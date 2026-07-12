#!/usr/bin/env python3
import os
import subprocess
import signal
import json
import time
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GLib

CONFIG_FILE = os.path.expanduser('~/.config/lenslink-tray.json')
scrcpy_process = None

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"mode": "camera0", "hidden": True, "orientation": "vertical"}

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception:
        pass

config = load_config()

def get_v4l2_device():
    try:
        output = subprocess.check_output(['v4l2-ctl', '--list-devices'], stderr=subprocess.DEVNULL).decode('utf-8')
        lines = output.splitlines()
        for i, line in enumerate(lines):
            if 'Android_Webcam' in line:
                if i + 1 < len(lines):
                    return lines[i+1].strip()
    except Exception:
        pass
    return None

def stop_scrcpy():
    global scrcpy_process
    if scrcpy_process:
        try:
            os.killpg(os.getpgid(scrcpy_process.pid), signal.SIGTERM)
        except Exception:
            pass
        scrcpy_process = None
    subprocess.run(['killall', '-9', 'scrcpy'], stderr=subprocess.DEVNULL)

def start_scrcpy():
    global scrcpy_process
    stop_scrcpy()
    time.sleep(0.5)
    
    dev = get_v4l2_device()
    if not dev:
        return
        
    cmd = ['scrcpy', f'--v4l2-sink={dev}', '--no-audio', '--max-size=1920']
    
    if config["hidden"]:
        cmd.append('--no-playback')
    else:
        cmd.append('--window-borderless')
        cmd.append('--window-title=LensLink Viewfinder')
        
    is_vertical = (config.get("orientation", "vertical") == "vertical")
    
    if config["mode"] == "camera0":
        cmd.extend(['--video-source=camera', '--camera-id=0', '--camera-ar=16:9'])
        if is_vertical:
            cmd.append('--capture-orientation=90')
        else:
            cmd.append('--capture-orientation=0')
    elif config["mode"] == "camera1":
        cmd.extend(['--video-source=camera', '--camera-id=1', '--camera-ar=16:9'])
        if is_vertical:
            cmd.append('--capture-orientation=90')
        else:
            cmd.append('--capture-orientation=0')
    elif config["mode"] == "mirror":
        cmd.extend(['--video-source=display'])
        # For mirror, we lock it to the phone's physical rotation at the time of launch
        # If they want vertical, they must hold it vertically. If horizontal, horizontally.
        cmd.append('--capture-orientation=@')
        
    scrcpy_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)

def main():
    icon_path = os.path.expanduser('~/.local/share/icons/lenslink_logo_black.png')
    
    indicator = AppIndicator3.Indicator.new(
        "lenslink-indicator",
        icon_path,
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS
    )
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    
    menu = Gtk.Menu()
    
    # Mode variables
    cam0_item = Gtk.RadioMenuItem.new_with_label(None, "Camera 0")
    cam1_item = Gtk.RadioMenuItem.new_with_label_from_widget(cam0_item, "Camera 1")
    mirror_item = Gtk.RadioMenuItem.new_with_label_from_widget(cam0_item, "Screen Mirror")
    
    if config["mode"] == "camera0":
        cam0_item.set_active(True)
    elif config["mode"] == "camera1":
        cam1_item.set_active(True)
    elif config["mode"] == "mirror":
        mirror_item.set_active(True)
        
    def set_mode(item, mode):
        if item.get_active():
            config["mode"] = mode
            save_config(config)
            threading.Thread(target=start_scrcpy).start()
            
    cam0_item.connect("toggled", set_mode, "camera0")
    cam1_item.connect("toggled", set_mode, "camera1")
    mirror_item.connect("toggled", set_mode, "mirror")
    
    menu.append(cam0_item)
    menu.append(cam1_item)
    menu.append(mirror_item)
    menu.append(Gtk.SeparatorMenuItem())
    
    # Orientation Toggle
    vert_item = Gtk.RadioMenuItem.new_with_label(None, "Orientation: Vertical (TikTok)")
    horiz_item = Gtk.RadioMenuItem.new_with_label_from_widget(vert_item, "Orientation: Horizontal (YouTube)")
    
    if config.get("orientation", "vertical") == "vertical":
        vert_item.set_active(True)
    else:
        horiz_item.set_active(True)
        
    def set_orientation(item, ori):
        if item.get_active():
            config["orientation"] = ori
            save_config(config)
            threading.Thread(target=start_scrcpy).start()
            
    vert_item.connect("toggled", set_orientation, "vertical")
    horiz_item.connect("toggled", set_orientation, "horizontal")
    
    menu.append(vert_item)
    menu.append(horiz_item)
    menu.append(Gtk.SeparatorMenuItem())
    
    hide_item = Gtk.CheckMenuItem.new_with_label("Toggle Window Visibility")
    hide_item.set_active(config["hidden"])
    
    def toggle_hide(item):
        config["hidden"] = item.get_active()
        save_config(config)
        threading.Thread(target=start_scrcpy).start()
        
    hide_item.connect("toggled", toggle_hide)
    menu.append(hide_item)
    menu.append(Gtk.SeparatorMenuItem())
    
    restart_item = Gtk.MenuItem.new_with_label("Restart Stream")
    restart_item.connect("activate", lambda _: threading.Thread(target=start_scrcpy).start())
    menu.append(restart_item)
    
    restart_adb_item = Gtk.MenuItem.new_with_label("Restart ADB")
    def restart_adb(_):
        stop_scrcpy()
        subprocess.run(['adb', 'kill-server'], stderr=subprocess.DEVNULL)
        subprocess.run(['adb', 'start-server'], stderr=subprocess.DEVNULL)
        threading.Thread(target=start_scrcpy).start()
    restart_adb_item.connect("activate", restart_adb)
    menu.append(restart_adb_item)
    
    quit_item = Gtk.MenuItem.new_with_label("Quit")
    def quit_app(_):
        stop_scrcpy()
        Gtk.main_quit()
    quit_item.connect("activate", quit_app)
    menu.append(quit_item)
    
    menu.show_all()
    indicator.set_menu(menu)
    
    threading.Thread(target=start_scrcpy).start()
    Gtk.main()

if __name__ == "__main__":
    main()
