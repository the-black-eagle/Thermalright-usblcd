/* Copyright 2005 Gary Moore (g.moore(AT)gmx.co.uk)

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/

#ifndef LCD_DRIVER_H
#define LCD_DRIVER_H
#pragma once

#include <array>
#include <chrono>
#include <cstdint>
#include <ctime>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <iomanip>

#include <libusb-1.0/libusb.h>
#include <opencv2/opencv.hpp>
#include <nlohmann/json.hpp>

class SystemInfoPoller
{
public:
  SystemInfoPoller(double fast_interval = 0.2, double slow_interval = 2.5);
  ~SystemInfoPoller();

  void start();
  void stop();
  std::unordered_map<std::string, double> get_info();
  std::vector<std::string> get_available_metrics();

private:
  struct CpuTimes
  {
    long long user = 0, nice = 0, system = 0, idle = 0, iowait = 0, irq = 0, softirq = 0, steal = 0;
    long long total() const;
    long long active() const;
  };

  // Member variables
  double fast_interval;
  double slow_interval;
  bool _running;
  void* nvml_handle;

  // NVML function typedefs
  typedef int (*nvmlInit_t)();
  typedef int (*nvmlShutdown_t)();
  typedef int (*nvmlDeviceGetCount_t)(unsigned int*);
  typedef int (*nvmlDeviceGetHandleByIndex_t)(unsigned int, void**);
  typedef int (*nvmlDeviceGetTemperature_t)(void*, int, unsigned int*);
  typedef int (*nvmlDeviceGetUtilizationRates_t)(void*, void*);
  typedef int (*nvmlDeviceGetClockInfo_t)(void*, int, unsigned int*);
  typedef int (*nvmlDeviceGetFanSpeed_t)(void*, unsigned int*);

  // NVML function pointers
  nvmlInit_t nvmlInit;
  nvmlShutdown_t nvmlShutdown;
  nvmlDeviceGetCount_t nvmlDeviceGetCount;
  nvmlDeviceGetHandleByIndex_t nvmlDeviceGetHandleByIndex;
  nvmlDeviceGetTemperature_t nvmlDeviceGetTemperature;
  nvmlDeviceGetUtilizationRates_t nvmlDeviceGetUtilizationRates;
  nvmlDeviceGetClockInfo_t nvmlDeviceGetClockInfo;
  nvmlDeviceGetFanSpeed_t nvmlDeviceGetFanSpeed;

  std::thread _thread;
  std::mutex _lock;
  std::unordered_map<std::string, double> info;

  CpuTimes _last_cpu_times;
  std::chrono::steady_clock::time_point _last_cpu_time;

  // NVML constants
  static constexpr int NVML_SUCCESS = 0;
  static constexpr int NVML_TEMPERATURE_GPU = 0;
  static constexpr int NVML_CLOCK_GRAPHICS = 0;

  // NVML structs
  struct nvmlUtilization_t
  {
    unsigned int gpu;
    unsigned int memory;
  };

  // Private methods
  void _poll_loop();
  void _merge_info(const std::unordered_map<std::string, double>& updated);
  std::unordered_map<std::string, double> _poll_fast();
  std::unordered_map<std::string, double> _poll_slow();

  // Helper methods
  void load_nvml();
  CpuTimes get_cpu_times();
  double get_cpu_percent();
  double get_cpu_temperature();
  std::pair<double, double> get_memory_info();
  double get_cpu_frequency();
  std::pair<double, double> get_disk_info();
  std::vector<int> get_gpu_stats();
  std::vector<int> get_amd_gpu_stats(std::string basePath);
  std::vector<int> get_intel_gpu_stats();
  std::vector<int> get_nvidia_gpu_stats();

  // Metric detection
  std::vector<std::string> detect_available_metrics();
  bool cpu_has_temp();
  bool meminfo_available();
  std::string amd_gpu_available();
  bool intel_gpu_available();
  bool nvidia_gpu_available();
};

class ImageConverter
{
public:
  // Preallocated version: caller gets three chunks already filled
  static std::array<std::vector<uint8_t>, 3> image_to_rgb565_chunks(const uint8_t* pixels_rgb);

private:
  static inline uint16_t rgb_to_rgb565(uint8_t r, uint8_t g, uint8_t b)
  {
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
  }
};

class VideoBackground
{
public:
  VideoBackground(const std::string& path, const std::string& mode = "loop", int target_fps = 24)
    : path(path),
      mode(mode),
      _fps(target_fps),
      _frame_index(0),
      _forward(true),
      _playing(false),
      _streaming(false)
  {
    _init();
  }

  ~VideoBackground() { stop(); }

  void start_playback();
  void stop();
  cv::Mat get_current_frame();
  bool is_loaded() const;
  size_t get_frame_count() const;
  std::string get_path() const { return path; }

private:
  std::string path;
  std::string mode;
  int _fps;
  std::vector<cv::Mat> _frames;
  size_t _frame_index;
  bool _forward;
  bool _playing;
  bool _streaming;
  std::thread _thread;
  cv::VideoCapture cap;

  cv::Mat _current_frame;
  std::mutex _lock;

  void _init();
  void _preload_frames();
  void _play_loop();
  void _stream_loop();
  void _preloaded_loop();
};

class BackgroundManager
{
public:
  BackgroundManager() : static_bg_path(""), static_bg_mtime(0) {}
  std::vector<uint8_t> get_background_bytes(const std::string& background_path = "");

private:
  cv::Mat create_default_background();
  cv::Mat load_static_background(const std::string& background_path);
  cv::Mat get_background(const std::string& background_path = "");

  cv::Mat static_bg;
  std::string static_bg_path;
  std::time_t static_bg_mtime;
  std::unique_ptr<VideoBackground> video_bg = nullptr;
  cv::Mat default_bg;
};

class ConfigManager {
public:
    explicit ConfigManager(const std::string& path);

    bool load_config(const std::string& path);

    std::string dump(int indent = 4) const;

    nlohmann::json get_value(const std::string& key) const;
    void set_value(const std::string& key, const nlohmann::json& value);

    bool load_config_from_defaults();
    nlohmann::json get_config() const { return _data; }  // Returns a copy, auto-converts to Python dict
    void update_config_value(const std::string& key, const nlohmann::json& value);
    bool save_config(const std::string& path) const;

private:
    void addDefaultModules();
    std::string _path;
    nlohmann::json _data;
};


// --- USB helpers ---

struct ScsiResult
{
  bool ok; // true if command passed (CSW status 0)
  uint8_t status; // raw CSW status (0, 1, or 2)
  std::vector<uint8_t> data; // IN data, if any
};

static std::mutex scsi_log_mutex;

bool init_dev(uint16_t vid = 0x0402, uint16_t pid = 0x3922);
static void scsi_log(const std::string &msg);

void cleanup_dev();
bool device_ready();
bool handshake_with_device();

void reset_transport();
void log_sense(const ScsiResult& result);

//internal routines

BackgroundManager& get_background_manager();
void update_lcd_image(const uint8_t* pil_img, libusb_device_handle* dev = nullptr);
ScsiResult send_scsi_command(libusb_device_handle* dev,
                             const std::vector<uint8_t>& cdb,
                             const std::vector<uint8_t>& data_out = {},
                             size_t data_in_len = 0, unsigned int tag = 0);

#endif // LCD_DRIVER_H