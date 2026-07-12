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
chmod +x ~/.local/bin/lenslink-app

# Update desktop database
update-desktop-database ~/.local/share/applications/
if command -v kbuildsycoca6 &> /dev/null; then
    kbuildsycoca6
fi

echo "LensLink installed successfully! You can launch it from your App Launcher."
