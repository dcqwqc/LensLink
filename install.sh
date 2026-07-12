#!/bin/bash

echo "Installing LensLink..."

# Create necessary directories
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/256x256/apps ~/.local/share/pixmaps

# Copy files
cp lenslink-app.py ~/.local/bin/lenslink-app
cp lenslink_logo.png ~/.local/share/icons/lenslink_logo_black.png
cp lenslink.desktop ~/.local/share/applications/

# Globally override the scrcpy Android icon
cp lenslink_logo.png ~/.local/share/icons/hicolor/256x256/apps/scrcpy.png
cp lenslink_logo.png ~/.local/share/pixmaps/scrcpy.png
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor

# Make executable
chmod +x ~/.local/bin/lenslink-app ./setup-loopback.sh 2>/dev/null

# Dependency check: the normalizer pipeline needs ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "WARNING: ffmpeg not found. LensLink needs it for glitch-free mode switching."
    echo "         Install it (e.g. 'sudo pacman -S ffmpeg') before use."
fi

# Update desktop database
update-desktop-database ~/.local/share/applications/
if command -v kbuildsycoca6 &> /dev/null; then
    kbuildsycoca6
fi

echo "LensLink installed successfully! You can launch it from your App Launcher."
echo
echo "IMPORTANT (one-time): for glitch-free camera <-> mirror switching, run:"
echo "    close OBS, then:  sudo ./setup-loopback.sh"
echo "This creates the two loopback devices the seamless pipeline needs."
