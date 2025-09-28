
- Disk % used
- Disk free space in Gb

get_info()
Returns an unordered map containing key:value pairs.

## 🚧 Notes

The poller can be run at custom speeds when polling if you instantiate it with values.
`poller = lcd_driver.CSystemInfoPoller(0.1, 5)`

First number is the speed to poll cpu and gpu stats, second is the speed to poll disk and memory stats.  If you do not  specify a speed, the defaults are 0.2 and 2.5 seconds respectively.# LCD Driver Backend API
## 📖 Overview

The backend driver (lcd_driver) provides access to the LCD device and configuration from C++ and Python. It handles:

USB communication with the LCD (via libusb).

Frame uploading and updates (via OpenCV).

Configuration management (via JSON).

The Python bindings allow frontends to control the device without touching C++ directly.

## 🛠 Module: lcd_driver

When built, the backend is exposed as a Python extension module:

`import lcd_driver
`

You can refer to the file **`bindings.cpp`**  to see exactly what is exposed to python from the driver.

### 📂 Classes
#### ConfigManager

Manages configuration (config.json). Defaults are embedded in the driver.

##### Methods

ConfigManager(path: str)
Create a manager for the config file.

`config_manager = lcd_driver.ConfigManager(config_file)`

load_config(path:str) -> bool
Load config from file. Returns True  if missing as it falls back to defaults.

get_config() -> dict
Get the full config as a Python dict.

load_config_from_defaults()
Populate config with defaults (used on first run), or to reset the configuration.

update_config_value(key: str, value: Any)
Update or add a config key.

save_config(path: str) -> bool
Save config to a given path.

#### LcdDriver

Handles the LCD device.

##### Methods

init_dev() -> bool
Initialize USB connection to LCD.

cleanup_dev()
Close connection.

get_background_manager()
Returns an instance of the background manager.

update_lcd_image(pil_img: list[uint8])
Sends exactly one frame to the lcd (raw PIL-style buffer).

#### Background Manager

Handles video or static backgrounds automatically

##### Methods

get_background_bytes(path:str)
Returns the raw bytes that make up the current image (either a video frame or a static background).  If no background path was specified, returns a default black background.

#### SystemInfoPoller

Periodically polls various metrics to display on the lcd.  Probes various metrics to determine if they are available.

##### Methods
start()
Starts the poller.

Stop()
Stops the poller.

get_available_metrics()
Returns a vector of strings containing the names of the metrics that the driver has detected are available.

Possible metrics available for display are 
- CPU temp
- CPU Frequency
- CPU Usage
- CPU Cores
- GPU Temp
- GPU Usage
- GPU Clock
- GPU Fan Speed
- % Memory used
- Memory used in Gb
- Disk % used
- Disk free space in Gb

get_info()
Returns an unordered map containing key:value pairs.

## 🚧 Notes

The poller can be run at custom speeds when polling if you instantiate it with values.
`poller = lcd_driver.CSystemInfoPoller(0.1, 5)`

First number is the speed to poll cpu and gpu stats, second is the speed to poll disk and memory stats.  If you do not  specify a speed, the defaults are 0.2 and 2.5 seconds respectively.