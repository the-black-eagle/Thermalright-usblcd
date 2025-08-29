# USB LCD Python Driver

This repo contains a pure Python driver for a USB-connected LCD panel (320×240, RGB565), which has been reverse-engineered from the original Windows software and now  is fully working under Linux.

The code here will only drive the Thermalright 2.4" LCD display that identifies itself as "ALi Corp. USBLCD" with vid:0402 & pid:3922.
This device identifies itself as a disk drive and is supplied with the Thermalright Frozen Warframe coolers.

This project allows you to send images and raw frames to the display without relying on proprietary software.  It can play 320x240 video as a background at roughly 20fps (windows version is 24fps) but there are command line options to alter the target frame rate and also the rate at which the overlaid info is fetched.

Various options are available - 

```
python sysmon.py --help
usage: sysmon.py [-h] [--background /home/lcdtest/background/01.png]
                 [--interval 0.5] [--video /home/lcdtest/video/01.mp4]
                 [--info-interval 0.5] [--video-mode {loop,pingpong}]

options:
  -h, --help            show this help message and exit
  --background /home/lcdtest/background/01.png
                        path to a 320x240 png
  --interval 0.5        Time to wait between frames if not playing video
  --video /home/lcdtest/video/01.mp4
                        path/to/a/320x240/video.mp4
  --info-interval 0.5   delay between updating info metrics (cpu info mainly)
                        in seconds
  --video-mode {loop,pingpong}
                        Loop at the end of the video or play backwards to the
                        beginning

```

If you don't choose any options, the script will choose sensible defaults and generate a gradient background.

---

## Features

- ✅ Supports **320×240 RGB565** frame format  
- ✅ Sends frames in the LCD’s expected 3-chunk USB protocol  
- ✅ Renders text and graphics using Pillow (`ImageDraw`, `ImageFont`)  
- ✅ Can display system stats (CPU, memory, etc.) using `psutil`  
- ✅ Verified working on Linux with `python-usb1` (`libusb1` bindings)

---

## Requirements

- Python **3.8+**  
- `libusb1` (`usb1` Python bindings)  
- [Pillow](https://pillow.readthedocs.io/)  
- [psutil](https://github.com/giampaolo/psutil)

Install system packages (Linux example):

```bash
sudo apt install libusb-1.0-0-dev
```

---

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/the-black-eagle/Thermalright-usblcd.git
cd usblcd-driver
pip install -r requirements.txt
```

---

## USB Permissions (udev)

By default, Linux may require root privileges to access USB devices. Add a **udev rule** and ensure your user is in the `plugdev` group so the driver can run without `sudo`.

1. Identify your LCD’s vendor and product ID:

```bash
lsusb
```

Example output:

```
Bus 001 Device 006: ID 0402:3922 ALi Corp. USBLCD
```

2. Create a udev rule:

```bash
sudo nano /etc/udev/rules.d/99-usblcd.rules
```

Add this line (replace `0402` and `3922` with your IDs):

```
SUBSYSTEM=="usb", ATTR{idVendor}=="0402", ATTR{idProduct}=="3922", GROUP="plugdev", MODE="0660"
```

3. Reload rules and replug device:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

4. Add your user to `plugdev` (if the group exists on your distro):

```bash
sudo usermod -aG plugdev $USER
```

Log out and back in for group changes to take effect.

> If your distribution doesn't use `plugdev`, replace `GROUP="plugdev"` with a group that makes sense on your distro (e.g. `users` or create a dedicated `usblcd` group).

---

## Usage

```bash
python sysmon.py --background /path/to/320x240.png

or

python sysmon.py
```

---

## Protocol Notes

- The LCD expects each frame split into **3 USB chunks**.  
- Chunks are column-interleaved; misordering produces interlaced/stretched output.  
- Pixel format: **RGB565 (little-endian)**.  
- The display must be refreshed periodically; otherwise it will reset. Maximum time between refreshes has been observed to be ~ 2 swconds.

---

## Development

This driver was built by reverse-engineering USB traffic from the vendor’s Windows application. Contributions welcome:

- Image scaling & dithering  
- Framebuffer management & buffering  
- Text/graphics overlay tools
- ~~mp4 playback as per the Windows version.~~ CPU intensive in pure python but working

---

## License

Apache License version 2.0. See [LICENSE](LICENSE) for details.

---

## Disclaimer

This project is not affiliated with or endorsed by the original vendor. Use at your own risk.
