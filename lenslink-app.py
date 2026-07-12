#!/usr/bin/env python3
import os
import subprocess
import signal
import json
import time
import threading
import fcntl
import sys

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GLib

CONFIG_FILE = os.path.expanduser('~/.config/lenslink-tray.json')
LOG_FILE = os.path.expanduser('~/.cache/lenslink.log')


def log(msg):
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass

# --- Pipeline architecture -------------------------------------------------
# scrcpy writes the phone stream (native resolution, which differs between the
# camera 1920x1080 landscape and the portrait screen-mirror) into an INTERNAL
# v4l2loopback device. A persistent ffmpeg pads/scales that to a CONSTANT
# 1920x1080 and writes it to the OUTPUT device that OBS reads.
#
# Because ffmpeg always emits the exact same format on the OUTPUT device, OBS
# locks onto that format once and every mode switch matches it -- so switching
# camera <-> mirror no longer glitches OBS, and OBS never needs restarting.
#
# The two devices are created by /etc/modprobe.d/v4l2loopback.conf (see
# install.sh / setup-loopback.sh). If the internal device is missing (setup not
# run yet) we fall back to the legacy single-device path so the app still runs.
OUTPUT_LABEL = "Android_Webcam"    # what OBS selects; held at a constant format
SOURCE_LABEL = "LensLink_Source"   # internal sink scrcpy writes to
OUT_W, OUT_H = 1080, 1920

scrcpy_process = None
ffmpeg_process = None

# Serialize stream (re)starts and coalesce bursts of mode clicks: each call
# bumps the generation, and a queued call bails if a newer one arrived.
_stream_lock = threading.Lock()
_stream_gen = 0

# Single-instance lock: without this, launching LensLink again (autostart +
# app launcher) stacks multiple copies that fight over the tray and the camera.
_instance_fh = None


def acquire_single_instance():
    global _instance_fh
    _instance_fh = open('/tmp/lenslink-app.lock', 'w')
    try:
        fcntl.flock(_instance_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"mode": "camera0", "hidden": True}


def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception:
        pass


config = load_config()


def find_device(label):
    """Return the /dev/videoN path whose v4l2 card label matches `label`."""
    try:
        output = subprocess.check_output(
            ['v4l2-ctl', '--list-devices'], stderr=subprocess.DEVNULL
        ).decode('utf-8')
    except Exception:
        return None
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if label in line:
            for j in range(i + 1, len(lines)):
                dev = lines[j].strip()
                if dev.startswith('/dev/video'):
                    return dev
                if dev == '':
                    break
    return None


def device_ready(dev, timeout=8.0):
    """Wait until `dev` reports a non-zero capture geometry (scrcpy is feeding)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            out = subprocess.check_output(
                ['v4l2-ctl', '-d', dev, '--get-fmt-video'],
                stderr=subprocess.DEVNULL,
            ).decode('utf-8')
            for line in out.splitlines():
                if 'Width/Height' in line:
                    dims = line.split(':', 1)[1].strip()
                    w, h = dims.split('/')
                    if int(w) > 0 and int(h) > 0:
                        return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def set_keep_format(dev, value):
    """Set the loopback device's keep_format control (runtime, no root).

    OUTPUT device (video0): keep_format=1 so its constant 1920x1080 survives
    the ffmpeg restart on a switch and OBS never sees the format drop.

    SOURCE device (video1): keep_format=0 -- it MUST change resolution between
    modes (portrait mirror vs landscape camera). If left at 1 it locks to the
    first mode's geometry and every later switch is mangled.
    """
    subprocess.run(['v4l2-ctl', '-d', dev, '-c', f'keep_format={value}'],
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def _kill(proc):
    """Terminate a process group and WAIT for it to exit, so its v4l2 device
    fds are actually released before we open them again. Not waiting is what
    wedged video0 on rapid switches (new ffmpeg opened it before the old one
    let go, so it attached to the input but never the output)."""
    if not proc:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        return
    try:
        proc.wait(timeout=2)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=1)
        except Exception:
            pass


def stop_stream():
    global scrcpy_process, ffmpeg_process
    # Kill ffmpeg (the video0 producer) FIRST and wait, then scrcpy.
    _kill(ffmpeg_process)
    _kill(scrcpy_process)
    ffmpeg_process = None
    scrcpy_process = None
    # Belt-and-suspenders for any orphans left by earlier crashes. Target only
    # OUR normalizer (an ffmpeg reading a v4l2 device) so we never kill an
    # unrelated ffmpeg the user may be running.
    subprocess.run(['killall', '-9', 'scrcpy'], stderr=subprocess.DEVNULL)
    subprocess.run(['pkill', '-9', '-f', 'ffmpeg.*-f v4l2 -i /dev/video'],
                   stderr=subprocess.DEVNULL)


def _scrcpy_source_args():
    if config["mode"] == "camera0":
        return ['--camera-size=1920x1080', '--video-source=camera', '--camera-id=0']
    elif config["mode"] == "camera1":
        return ['--camera-size=1920x1080', '--video-source=camera', '--camera-id=1']
    elif config["mode"] == "mirror":
        return ['--video-source=display']
    return ['--camera-size=1920x1080', '--video-source=camera', '--camera-id=0']


def _window_args():
    """When preview is on, the SAME scrcpy that feeds the sink also shows its
    playback window (the real phone feed). When off, it runs headless.
    Note: closing that window closes scrcpy -> use the menu toggle to hide it."""
    if config.get("preview"):
        return ['--window-title=LensLink Viewfinder']
    return ['--no-window']


def start_stream():
    global scrcpy_process, ffmpeg_process, _stream_gen
    _stream_gen += 1
    my_gen = _stream_gen
    with _stream_lock:
        if my_gen != _stream_gen:
            return  # a newer switch superseded this one while we waited
        stop_stream()
        time.sleep(0.5)

        out_dev = find_device(OUTPUT_LABEL)
        src_dev = find_device(SOURCE_LABEL)
        log(f"start_stream mode={config['mode']} out={out_dev} src={src_dev}")
        if not out_dev:
            log("  ABORT: no output device found")
            return  # nothing to write to

        _start_stream_locked(out_dev, src_dev, my_gen)


def _start_stream_locked(out_dev, src_dev, my_gen):
    global scrcpy_process, ffmpeg_process

    # Hold the OBS-facing format across the ffmpeg restart on every switch,
    # but let the internal device change resolution freely between modes.
    set_keep_format(out_dev, 1)
    if src_dev:
        set_keep_format(src_dev, 0)

    if src_dev:
        # --- Normalized two-stage pipeline (seamless mode switching) --------
        scrcpy_cmd = ['scrcpy', f'--v4l2-sink={src_dev}', '--no-audio'] \
            + _window_args() + _scrcpy_source_args()
        scrcpy_process = subprocess.Popen(
            scrcpy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid)

        if not device_ready(src_dev):
            log("  ABORT: scrcpy never produced frames on src device")
            return  # scrcpy never produced frames (phone unplugged, etc.)
        if my_gen != _stream_gen:
            log("  superseded during warmup; not starting ffmpeg")
            return
        log("  src ready; starting ffmpeg normalizer")

        # Pad/scale whatever scrcpy produced to a constant OUT_WxOUT_H so the
        # OUTPUT device's format never changes between modes.
        vf = (f'scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,'
              f'pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=black,'
              f'format=yuv420p')
        ffmpeg_cmd = ['ffmpeg', '-nostdin', '-fflags', 'nobuffer',
                      '-flags', 'low_delay', '-f', 'v4l2', '-i', src_dev,
                      '-vf', vf, '-f', 'v4l2', '-pix_fmt', 'yuv420p', out_dev]
        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid)
    else:
        # --- Legacy fallback: setup not run yet, write straight to OBS device.
        scrcpy_cmd = ['scrcpy', f'--v4l2-sink={out_dev}', '--no-audio'] \
            + _window_args() + _scrcpy_source_args()
        scrcpy_process = subprocess.Popen(
            scrcpy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid)


def main():
    icon_path = os.path.expanduser('~/.local/share/icons/lenslink_logo_black.png')

    indicator = AppIndicator3.Indicator.new(
        "lenslink-indicator",
        icon_path,
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS
    )
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

    menu = Gtk.Menu()

    # Plain menu items -- NOT RadioMenuItem. The radio group's activate/toggle
    # cascade (set_active on one item re-fires activate on the others) storms
    # events over the SNI/DBusMenu tray and restarts the stream in a loop. We
    # instead track the current mode with a checkmark in the label.
    MODES = [("camera0", "Camera 0"), ("camera1", "Camera 1"), ("mirror", "Screen Mirror")]
    mode_items = {}

    def refresh_labels():
        for m, label in MODES:
            mark = "● " if config["mode"] == m else "○ "
            mode_items[m].set_label(mark + label)

    def on_mode(item, mode):
        log(f"mode click -> {mode}")
        config["mode"] = mode
        save_config(config)
        refresh_labels()
        threading.Thread(target=start_stream).start()

    for m, label in MODES:
        it = Gtk.MenuItem.new_with_label(label)
        it.connect("activate", on_mode, m)
        mode_items[m] = it
        menu.append(it)
    refresh_labels()

    menu.append(Gtk.SeparatorMenuItem())

    # Preview toggle: plain item with a label that flips (same robust pattern
    # as the mode items -- no CheckMenuItem toggle-state over the SNI tray).
    preview_item = Gtk.MenuItem.new_with_label("")

    def refresh_preview_label():
        preview_item.set_label("Hide Preview Window" if config.get("preview")
                               else "Show Preview Window")

    def on_preview(_):
        config["preview"] = not config.get("preview")
        save_config(config)
        refresh_preview_label()
        log(f"preview -> {config['preview']}")
        threading.Thread(target=start_stream).start()

    preview_item.connect("activate", on_preview)
    refresh_preview_label()
    menu.append(preview_item)

    menu.append(Gtk.SeparatorMenuItem())

    restart_item = Gtk.MenuItem.new_with_label("Restart Stream")
    restart_item.connect("activate", lambda _: threading.Thread(target=start_stream).start())
    menu.append(restart_item)

    restart_adb_item = Gtk.MenuItem.new_with_label("Restart ADB")
    def restart_adb(_):
        stop_stream()
        subprocess.run(['adb', 'kill-server'], stderr=subprocess.DEVNULL)
        subprocess.run(['adb', 'start-server'], stderr=subprocess.DEVNULL)
        threading.Thread(target=start_stream).start()
    restart_adb_item.connect("activate", restart_adb)
    menu.append(restart_adb_item)

    quit_item = Gtk.MenuItem.new_with_label("Quit")
    def quit_app(_):
        stop_stream()
        Gtk.main_quit()
    quit_item.connect("activate", quit_app)
    menu.append(quit_item)

    menu.show_all()
    indicator.set_menu(menu)

    threading.Thread(target=start_stream).start()
    Gtk.main()


if __name__ == "__main__":
    if not acquire_single_instance():
        sys.stderr.write("LensLink is already running; exiting this copy.\n")
        sys.exit(0)
    main()
