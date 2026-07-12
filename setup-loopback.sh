#!/bin/bash
#
# One-time root setup for LensLink's seamless mode switching.
#
# Creates TWO v4l2loopback devices:
#   /dev/video0  "Android_Webcam"  -> the device OBS selects (constant 1920x1080)
#   /dev/video1  "LensLink_Source" -> internal sink that scrcpy writes to
#
# and enables keep_format=1 so the OBS-facing format survives the brief producer
# swap when you change modes. This is what lets you switch camera <-> screen
# mirror without OBS ever glitching or needing a restart.
#
# Usage:  close OBS, then:  sudo ./setup-loopback.sh
#
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root:  sudo $0"
    exit 1
fi

CONF=/etc/modprobe.d/v4l2loopback.conf
# Labels have no spaces, so no per-item quotes (quotes would get embedded in
# the label). keep_format is a runtime control, not a module param here, so the
# app sets it at launch instead.
echo 'options v4l2loopback video_nr=0,1 card_label=Android_Webcam,LensLink_Source exclusive_caps=1,1 max_buffers=4' > "$CONF"
echo "v4l2loopback" > /etc/modules-load.d/v4l2loopback.conf
echo "Wrote $CONF"

# Refuse to reload while something is holding a loopback device (e.g. OBS),
# because modprobe -r would fail and leave you with the old single device.
if fuser /dev/video0 >/dev/null 2>&1; then
    echo
    echo "!! /dev/video0 is in use (is OBS or a browser open?)."
    echo "!! Close it and re-run, or just reboot to apply."
    exit 1
fi

echo "Reloading v4l2loopback..."
modprobe -r v4l2loopback 2>/dev/null || true
modprobe v4l2loopback

echo
echo "Done. Current loopback devices:"
v4l2-ctl --list-devices | grep -A1 -E "Android_Webcam|LensLink_Source"
