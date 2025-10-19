# LCD System Monitor (Linux Driver + GUI)

[![Build AppImage](https://github.com/the-black-eagle/Thermalright-usblcd/actions/workflows/build-appimage.yml/badge.svg)](https://github.com/the-black-eagle/Thermalright-usblcd/actions/workflows/build-appimage.yml)
[![Latest Release](https://img.shields.io/github/v/release/the-black-eagle/Thermalright-usblcd?label=Latest%20AppImage&logo=github)](https://github.com/the-black-eagle/Thermalright-usblcd/releases/latest)
[![License](https://img.shields.io/github/license/the-black-eagle/Thermalright-usblcd)](LICENSE)

---

### 🧱 Build Status & Releases

- **Build AppImage:** Shows the current CI build status for the latest tagged release.  
- **Latest AppImage:** Links directly to the most recent prebuilt AppImage binary.  
- **License:** Indicates the open-source license for this project.  

These badges update automatically when a new tag is pushed or a release is published, ensuring the README always reflects the latest build and release state.

### ⚡ Quick Install

You can download the latest AppImage directly from the [**Releases**](https://github.com/the-black-eagle/Thermalright-usblcd/releases/latest) page.

```bash
wget https://github.com/the-black-eagle/Thermalright-usblcd/releases/latest/download/tr-driver-x86_64.AppImage
chmod +x tr-driver-x86_64.AppImage
./tr-driver-x86_64.AppImage
```


That’s it — no installation required!
The AppImage bundles all dependencies, so it runs on most modern Linux distributions. It includes 440 static images and 596 video files.

### ⚙️ Driver Overview

This driver is specifically for the Thermalright LCD that idetifies itself as **ALi Corp. USBLCD** and has vid of 0402 and a pid of 3922.  It will not drive any other
Thermalright LCD's.  Thermalright have no intentions of providing a Linux driver (because I asked them) so I did it myself.  The result is as close to the original as I could get.  The program can display static or video images oon the LCD.  If you use static images with transparency (alpha channel) and then load a video, the video will play in the alpha channel of the image.

Date and time formatting follows standard %y-%m formatting etc but can include `\n` for new lines which is used in some of the provided images to stack the day on top of the date.

Most of the preview images have been edited from the originals supplied by ThermalRight to better fit Linux and this project, although some do still contain the Vendor name and some chinese text.  This is only in the media selector though, the actual loaded image will not contain that.
Videos have been copied `as is` from the vendor website.  Their original downloads them on demand.  Images, videos and the config files for the images can be found in the **USBLCD** directory.

Program can be sent to the systray by clicking the close box and will continue to run in the background.  The GUI will not be updated in this case, just your LCD.

This project is a work in progress but it is stable enough now to be used with one caveat - I have not yet figured out how to interrupt the start-up animation, so
users need to wait for the LCD to time out ~1 minute.  There is some code in the driver to do the initial handshake but it's not in a working state yet.  If the driver loses comms with the LCD for some reason (shouldn't happen but just in case), it will bring itself to the front and notify you with a message box.  Once the LCD has stopped playing it's start-up animation, click OK to resume things.  In practice, this is unlikely to happen though.

### Please Note

I am unable to test the nVidia or Intel stuff, so although I *think* it should work, it's totally untested!!

- ✅ Native Linux replacement for the original closed-source Windows tool.  
- ✅ Backend in C++ (handles device comms, config, frame uploads).  
- ✅ Python GUI frontend for preview/testing (swappable for other UIs).  
- ✅ Config stored in JSON, managed by the backend.  

---

## ⚙️ Requirements

### System
- Linux (tested on Ubuntu 24.04, GNOME/Mutter)  
- USB access to the LCD device  

### Build Dependencies

| Dependency | Purpose | Install (Ubuntu/Debian) | Link |
|------------|---------|--------------------------|------|
| **g++ / clang++** | Build C++17 code | `sudo apt install g++` | [GCC](https://gcc.gnu.org/) |
| **CMake ≥ 3.16** | Build system | `sudo apt install cmake` | [CMake](https://cmake.org/download/) |
| **libusb-1.0** | USB device access | `sudo apt install libusb-1.0-0-dev` | [libusb](https://libusb.info/) |
| **Python 3.12+** | Frontend GUI | `sudo apt install python3 python3-dev python3-pip` | [Python](https://www.python.org/) |
| **pybind11** | Python bindings | `pip install pybind11` | [pybind11](https://github.com/pybind/pybind11) |
| **pybind11_json** | JSON conversion | `pip install pybind11_json` | [pybind11_json](https://github.com/pybind/pybind11_json) |
| **nlohmann/json** | JSON handling (C++) | `sudo apt install nlohmann-json3-dev` | [nlohmann/json](https://github.com/nlohmann/json) |
| **OpenCV** | Image/frame processing | `sudo apt install libopencv-dev` | [OpenCV](https://opencv.org/) |

---

## 🔨 Build & Run

### Quick start (one-liner)
```bash
git clone https://github.com/yourname/lcd-sysmon.git
cd lcd-sysmon
mkdir build && cd build
cmake ..
make run
```

👉 `make run` will **build** the backend and **launch** the Python GUI in one step.  

---

### Step-by-step (if you prefer)
```bash
git clone https://github.com/yourname/lcd-sysmon.git
cd lcd-sysmon
mkdir build && cd build
cmake ..
make             # builds the driver + copies gui_controller.py
python3 gui_controller.py
```

---

## 📂 Project Structure

```
lcd-sysmon/
├── src/
│   ├── CLcdDriver.cpp
│   ├── CLcdDriver.h
│   └── bindings.cpp
├── python/
│   └── gui_controller.py
│   └── background_selector.py
│   └── themed_messagebox.py
├── CMakeLists.txt
└── README.md
```

---

## ▶️ Usage

- On first run, no `config.json` exists → defaults are provided by the backend.  
- When settings are saved in the GUI, `config.json` is written to the working directory.  
- GUI runs at **25 fps** when focused, slows to conserve CPU when unfocused.  

---

## 🚀 Future Plans
- Alternative frontends (Electron, GTK, etc.).  
- Packaging (`.deb`, Flatpak).  
- Advanced minimize detection under GNOME (Xlib `_NET_WM_STATE_HIDDEN`).

Further dcumentation can be found in the `docs` directory.


## 🖥️ Screenshots

![Main UI](docs/screenshots/screen2.png)

![Selecting a video](docs/screenshots/screen1.png)
