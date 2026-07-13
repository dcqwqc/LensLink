# LensLink

LensLink is a professional, native Linux system tray application that turns your Android phone into a high-quality, borderless virtual webcam. It is powered entirely by [scrcpy](https://github.com/Genymobile/scrcpy) and native GTK `AppIndicator3`.

<img src="lenslink_logo.png" width="128" />

## Features
- **Native GTK System Tray:** Uses bulletproof `AppIndicator3` integration. No floating fallback windows.
- **Hardware Integration:** Toggle between Main Camera (0), Front Camera (1), or Screen Mirroring.
- **Invisible Mode:** Instantly toggle window visibility. When hidden, the camera feed runs entirely headless in the background via `v4l2loopback`.
- **Borderless Viewfinder:** When the camera window is visible, all OS titlebars and borders are stripped away for a completely clean feed.
- **Global Icon Override:** Replaces the generic `scrcpy` Wayland/X11 icons with a minimalist line-art camera logo.
- **Quick Controls:** Restart the video stream or reboot the ADB server straight from your taskbar.

## Dependencies
LensLink requires the following to be installed on your Linux system:
- `scrcpy` (version 2.0 or higher recommended)
- `v4l2loopback-dkms` (for the virtual webcam driver)
- `android-tools` (for `adb`)
- `python3`, `python-gobject`, `libappindicator-gtk3`

## Installation

1. Clone this repository:
```bash
git clone https://github.com/dcqwqc/LensLink.git
cd LensLink
```

2. Run the install script:
```bash
chmod +x install.sh
./install.sh
```

3. Launch **LensLink** from your Application Launcher, or run `~/.local/bin/lenslink-app` directly.

## Usage
1. Connect your Android phone via USB.
2. Launch LensLink. The icon will appear in your system tray.
3. Right-click the tray icon to select your preferred camera or screen mirror mode.
4. Open OBS Studio or Discord, and select `Android_Webcam` as your Video Capture Device.

### Important: Orientation and OBS
The "Output: Vertical / Horizontal" toggle changes video0's actual output resolution.
- **One thing to remember:** Flipping this toggle will mismatch OBS's cached format until OBS re-negotiates. You MUST deactivate and reactivate the source in OBS right after changing this setting.
- Since your OBS is vertical, just leave it on **Output: Vertical**. Both the phone mirror and cameras will output as 1080x1920 (an exact match), keeping the feed clean so OBS never has to reconnect.
- Only touch this toggle if you ever reconfigure OBS to a horizontal canvas.

## Credits & Acknowledgements
This project is built directly on top of [scrcpy](https://github.com/Genymobile/scrcpy) by Genymobile. All video encoding, decoding, and V4L2 integration is handled by their incredible open-source engine.

## License
MIT License
