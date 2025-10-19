/* Copyright 2025 the-black-eagle (18698554+the-black-eagle@users.noreply.github.com)

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

#include "CLcdDriver.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <numeric>
#include <sstream>

#include <dlfcn.h>
#include <libusb-1.0/libusb.h>

static constexpr int WIDTH = 320;
static constexpr int HEIGHT = 240;
static uint32_t TAG = 1;
static bool DEBUG = false;
BackgroundManager bg_manager;

SystemInfoPoller::SystemInfoPoller(double fast_interval, double slow_interval)
  : fast_interval(fast_interval),
    slow_interval(slow_interval),
    _running(false),
    nvml_handle(nullptr),
    nvmlInit(nullptr),
    nvmlShutdown(nullptr),
    nvmlDeviceGetCount(nullptr),
    nvmlDeviceGetHandleByIndex(nullptr),
    nvmlDeviceGetTemperature(nullptr),
    nvmlDeviceGetUtilizationRates(nullptr),
    nvmlDeviceGetClockInfo(nullptr),
    nvmlDeviceGetFanSpeed(nullptr)
{
  // Try to load NVML if we detect NVIDIA GPU
  if (nvidia_gpu_available())
  {
    load_nvml();
  }

  auto detected = detect_available_metrics();
  for (const auto& metric : detected)
  {
    info[metric] = 0.0;
  }

  // Initialize CPU tracking for percentage calculation
  _last_cpu_times = get_cpu_times();
  _last_cpu_time = std::chrono::steady_clock::now();
}

SystemInfoPoller::~SystemInfoPoller()
{
  stop(); // ensures clean shutdown
}

void SystemInfoPoller::start()
{
  if (_running)
    return;
  _running = true;
  _thread = std::thread(&SystemInfoPoller::_poll_loop, this);
}

void SystemInfoPoller::stop()
{
  _running = false;
  if (_thread.joinable())
  {
    _thread.join();
  }
}

std::unordered_map<std::string, double> SystemInfoPoller::get_info()
{
  std::lock_guard<std::mutex> lock(_lock);
  return info;
}

std::vector<std::string> SystemInfoPoller::get_available_metrics()
{
  std::vector<std::string> keys;
  for (auto& kv : info)
  {
    keys.push_back(kv.first);
  }
  return keys;
}

// CpuTimes methods
long long SystemInfoPoller::CpuTimes::total() const
{
  return user + nice + system + idle + iowait + irq + softirq + steal;
}

long long SystemInfoPoller::CpuTimes::active() const
{
  return total() - idle - iowait;
}

void SystemInfoPoller::_poll_loop()
{
  double next_fast = 0;
  double next_slow = 0;
  while (_running)
  {
    double now =
        std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();

    if (now >= next_fast)
    {
      auto updated = _poll_fast();
      _merge_info(updated);
      next_fast = now + fast_interval;
    }
    if (now >= next_slow)
    {
      auto updated = _poll_slow();
      _merge_info(updated);
      next_slow = now + slow_interval;
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
}

void SystemInfoPoller::_merge_info(const std::unordered_map<std::string, double>& updated)
{
  if (updated.empty())
    return;
  std::lock_guard<std::mutex> lock(_lock);
  for (auto& kv : updated)
  {
    info[kv.first] = kv.second;
  }
}

std::unordered_map<std::string, double> SystemInfoPoller::_poll_fast()
{
  std::unordered_map<std::string, double> out;

  // CPU percentage
  try
  {
    double percent = get_cpu_percent();
    if (percent > 0 && percent < 101)
      out["cpu_percent"] = percent;
  }
  catch (...)
  {
  }

  // CPU temperature
  try
  {
    double cputemp = get_cpu_temperature();
    if (cputemp > 15 && cputemp < 100) // sane values
      out["cpu_temp"] = cputemp;
  }
  catch (...)
  {
  }

  // CPU frequency
  try
  {
    double cpufreq = get_cpu_frequency();
    if (cpufreq > 0)
      out["cpu_freq"] = cpufreq;
  }
  catch (...)
  {
  }

  // GPU stats
  try
  {
    auto gpu_stats = get_gpu_stats();
    if (gpu_stats[0] > 0 && gpu_stats[0] < 101)
      out["gpu_temp"] = gpu_stats[0];
    if (gpu_stats[1] > -1)
      out["gpu_usage"] = gpu_stats[1];
    if (gpu_stats[2] > 0)
      out["gpu_clock"] = gpu_stats[2];
    if (gpu_stats.size() > 3 && gpu_stats[3] > -1)
    {
      out["gpu_fan"] = gpu_stats[3];
    }
  }
  catch (...)
  {
  }

  return out;
}

std::unordered_map<std::string, double> SystemInfoPoller::_poll_slow()
{
  std::unordered_map<std::string, double> out;

  // CPU count
  try
  {
    out["cpu_count"] = static_cast<double>(std::thread::hardware_concurrency());
  }
  catch (...)
  {
  }

  // Disk info
  try
  {
    auto disk_info = get_disk_info();
    if (disk_info.first > 0)
      out["disk_percent"] = disk_info.first;
    if (disk_info.second > 0)
      out["disk_free_gb"] = disk_info.second;
  }
  catch (...)
  {
  }

  // Memory info
  try
  {
    auto mem_info = get_memory_info();
    if (mem_info.first > 0)
      out["mem_percent"] = mem_info.first;
    if (mem_info.second > 0)
      out["mem_used_gb"] = mem_info.second;
  }
  catch (...)
  {
  }

  return out;
}

void SystemInfoPoller::load_nvml()
{
  // Try different possible library names/paths
  std::vector<std::string> nvml_paths = {
      "libnvidia-ml.so.1", "libnvidia-ml.so", "/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1",
      "/usr/lib64/libnvidia-ml.so.1", "/usr/local/cuda/lib64/libnvidia-ml.so.1"};

  for (const auto& path : nvml_paths)
  {
    nvml_handle = dlopen(path.c_str(), RTLD_LAZY);
    if (nvml_handle)
    {
      break;
    }
  }

  if (!nvml_handle)
  {
    return;
  }

  // Load function pointers
  nvmlInit = (nvmlInit_t)dlsym(nvml_handle, "nvmlInit_v2");
  if (!nvmlInit)
    nvmlInit = (nvmlInit_t)dlsym(nvml_handle, "nvmlInit");

  nvmlShutdown = (nvmlShutdown_t)dlsym(nvml_handle, "nvmlShutdown");
  nvmlDeviceGetCount = (nvmlDeviceGetCount_t)dlsym(nvml_handle, "nvmlDeviceGetCount_v2");
  if (!nvmlDeviceGetCount)
    nvmlDeviceGetCount = (nvmlDeviceGetCount_t)dlsym(nvml_handle, "nvmlDeviceGetCount");

  nvmlDeviceGetHandleByIndex =
      (nvmlDeviceGetHandleByIndex_t)dlsym(nvml_handle, "nvmlDeviceGetHandleByIndex_v2");
  if (!nvmlDeviceGetHandleByIndex)
    nvmlDeviceGetHandleByIndex =
        (nvmlDeviceGetHandleByIndex_t)dlsym(nvml_handle, "nvmlDeviceGetHandleByIndex");

  nvmlDeviceGetTemperature =
      (nvmlDeviceGetTemperature_t)dlsym(nvml_handle, "nvmlDeviceGetTemperature");
  nvmlDeviceGetUtilizationRates =
      (nvmlDeviceGetUtilizationRates_t)dlsym(nvml_handle, "nvmlDeviceGetUtilizationRates");
  nvmlDeviceGetClockInfo = (nvmlDeviceGetClockInfo_t)dlsym(nvml_handle, "nvmlDeviceGetClockInfo");
  nvmlDeviceGetFanSpeed = (nvmlDeviceGetFanSpeed_t)dlsym(nvml_handle, "nvmlDeviceGetFanSpeed");

  // Initialize NVML
  if (nvmlInit && nvmlInit() != NVML_SUCCESS)
  {
    dlclose(nvml_handle);
    nvml_handle = nullptr;
  }
  else if (nvmlInit)
  {
  }
}

SystemInfoPoller::CpuTimes SystemInfoPoller::get_cpu_times()
{
  CpuTimes times;
  std::ifstream file("/proc/stat");
  std::string line;
  if (std::getline(file, line) && line.substr(0, 3) == "cpu")
  {
    std::istringstream iss(line);
    std::string cpu;
    iss >> cpu >> times.user >> times.nice >> times.system >> times.idle >> times.iowait >>
        times.irq >> times.softirq >> times.steal;
  }
  return times;
}

double SystemInfoPoller::get_cpu_percent()
{
  auto now = std::chrono::steady_clock::now();
  auto current_times = get_cpu_times();

  auto time_diff =
      std::chrono::duration_cast<std::chrono::milliseconds>(now - _last_cpu_time).count();
  if (time_diff < 100)
  { // Too soon, return cached value
    return 0.0;
  }

  long long total_diff = current_times.total() - _last_cpu_times.total();
  long long active_diff = current_times.active() - _last_cpu_times.active();

  double cpu_percent = 0.0;
  if (total_diff > 0)
  {
    cpu_percent = (static_cast<double>(active_diff) / total_diff) * 100.0;
  }

  _last_cpu_times = current_times;
  _last_cpu_time = now;

  return cpu_percent;
}

double SystemInfoPoller::get_cpu_temperature()
{
  double max_temp = 0.0;

  // Iterate through hwmon devices to find CPU temperature sensors
  for (int i = 0; i < 10; ++i)
  { // Check hwmon0 through hwmon9
    std::string hwmon_path = "/sys/class/hwmon/hwmon" + std::to_string(i);
    std::string name_path = hwmon_path + "/name";

    std::ifstream name_file(name_path);
    if (!name_file.is_open())
      continue;

    std::string sensor_name;
    std::getline(name_file, sensor_name);
    name_file.close();

    // Check if this is a CPU temperature sensor
    if (sensor_name == "k10temp" || sensor_name == "coretemp")
    {
      // Found CPU sensor, now check for temperature inputs
      for (int temp_idx = 1; temp_idx <= 5; ++temp_idx)
      { // Check temp1_input through temp5_input
        std::string temp_path = hwmon_path + "/temp" + std::to_string(temp_idx) + "_input";
        std::ifstream temp_file(temp_path);

        if (temp_file.is_open())
        {
          int temp_millicelsius;
          if (temp_file >> temp_millicelsius)
          {
            double temp_celsius = temp_millicelsius / 1000.0;
            max_temp = std::max(max_temp, temp_celsius);
          }
          temp_file.close();
        }
      }
    }
  }

  return max_temp;
}

std::pair<double, double> SystemInfoPoller::get_memory_info()
{
  std::ifstream file("/proc/meminfo");
  std::string line;
  long long mem_total = 0, mem_available = 0;

  while (std::getline(file, line))
  {
    if (line.find("MemTotal:") == 0)
    {
      std::istringstream iss(line);
      std::string label, kb;
      iss >> label >> mem_total >> kb;
    }
    else if (line.find("MemAvailable:") == 0)
    {
      std::istringstream iss(line);
      std::string label, kb;
      iss >> label >> mem_available >> kb;
    }
  }

  if (mem_total > 0)
  {
    long long mem_used = mem_total - mem_available;
    double mem_percent = (static_cast<double>(mem_used) / mem_total) * 100.0;
    double mem_used_gb = (mem_used * 1024.0) / (1024.0 * 1024.0 * 1024.0); // KB to GB
    return {mem_percent, mem_used_gb};
  }

  return {0.0, 0.0};
}

double SystemInfoPoller::get_cpu_frequency()
{
  std::ifstream file("/proc/cpuinfo");
  std::string line;
  double freq = 0.0;

  while (std::getline(file, line))
  {
    if (line.find("cpu MHz") != std::string::npos)
    {
      size_t pos = line.find(':');
      if (pos != std::string::npos)
      {
        std::string freq_str = line.substr(pos + 1);
        freq_str.erase(0, freq_str.find_first_not_of(" \t"));
        try
        {
          freq = std::stod(freq_str);
          break;
        }
        catch (...)
        {
        }
      }
    }
  }

  return freq;
}

std::pair<double, double> SystemInfoPoller::get_disk_info()
{
  long long total_bytes = 0, used_bytes = 0, free_bytes = 0;

  // Read mount points from /proc/mounts
  std::ifstream mounts("/proc/mounts");
  std::string line;

  while (std::getline(mounts, line))
  {
    std::istringstream iss(line);
    std::string device, mountpoint, fstype;
    iss >> device >> mountpoint >> fstype;

    // Skip virtual/temporary filesystems
    if (fstype == "tmpfs" || fstype == "devtmpfs" || fstype == "proc" || fstype == "sysfs" ||
        fstype == "cgroup" || fstype == "overlay" || fstype == "squashfs" || fstype == "ramfs" ||
        fstype.empty())
    {
      continue;
    }

    if (device.find("/dev/loop") == 0 || device.find("/dev/sr") == 0)
    {
      continue;
    }

    if (mountpoint.find("/run") != std::string::npos)
    {
      continue;
    }

    // Get disk usage using statvfs-like approach
    try
    {
      auto space = std::filesystem::space(mountpoint);
      total_bytes += space.capacity;
      free_bytes += space.free;
      used_bytes += (space.capacity - space.free);
    }
    catch (...)
    {
      continue;
    }
  }

  double disk_percent = 0.0;
  double disk_free_gb = 0.0;

  if (total_bytes > 0)
  {
    disk_percent = (static_cast<double>(used_bytes) / total_bytes) * 100.0;
    disk_free_gb = static_cast<double>(free_bytes) / 1e9;
    return {disk_percent, disk_free_gb};
  }
  return {0.0, 0.0};
}

std::vector<int> SystemInfoPoller::get_gpu_stats()
{
  std::vector<int> stats = {0, 0, 0, 0}; // temp, usage, clock, fan

  // Try AMD GPU first
  std::string amdpath = amd_gpu_available();
  if (!amdpath.empty())
  {
    return get_amd_gpu_stats(amdpath);
  }

  // Try Intel GPU
  if (intel_gpu_available())
  {
    return get_intel_gpu_stats();
  }

  // Try NVIDIA GPU
  if (nvidia_gpu_available())
  {
    return get_nvidia_gpu_stats();
  }

  return stats;
}

std::vector<int> SystemInfoPoller::get_amd_gpu_stats(std::string basePath)
{
  std::vector<int> stats = {-1, -1, -1, -1};
  std::string file;

  // Temperature
  file = basePath + "/temp1_input";
  std::ifstream temp_file(file);
  if (temp_file.is_open())
  {
    int temp_millicelsius;
    if (temp_file >> temp_millicelsius)
    {
      stats[0] = static_cast<int>(std::round(temp_millicelsius / 1000.0));
    }
  }

  // GPU usage
  std::ifstream usage_file("/sys/class/drm/card1/device/gpu_busy_percent");
  if (usage_file.is_open())
  {
    int usage = -1;
    if (usage_file >> usage)
    {
      stats[1] = static_cast<int>(usage);
    }
  }

  // GPU clock
  file = basePath + "/freq1_input";
  std::ifstream clock_file(file);
  if (clock_file.is_open())
  {
    int temp_clockspeed;

    if (clock_file >> temp_clockspeed)
    {
      stats[2] = static_cast<int>(std::round(temp_clockspeed / 1000000.0));
    }
  }

  // Fan speed
  file = basePath + "/fan1_input";
  std::ifstream fan_file(file);
  if (fan_file.is_open())
  {
    int fan_pwm;

    if (fan_file >> fan_pwm)
    {
      stats[3] = static_cast<int>(fan_pwm); // Convert to percentage
    }
  }

  return stats;
}

std::vector<int> SystemInfoPoller::get_intel_gpu_stats()
{
  std::vector<int> stats = {0, 0, 0};

  // Intel GPU stats are more limited in sysfs
  // Temperature and basic frequency info
  std::ifstream freq_file("/sys/class/drm/card0/gt/gt0/freq0_cur_freq");
  if (freq_file.is_open())
  {
    long long freq_hz;
    if (freq_file >> freq_hz)
    {
      stats[2] = freq_hz / 1000000.0; // Hz to MHz
    }
  }

  return stats;
}

std::vector<int> SystemInfoPoller::get_nvidia_gpu_stats()
{
  std::vector<int> stats = {0, 0, 0, 0};

  if (!nvml_handle || !nvmlDeviceGetCount || !nvmlDeviceGetHandleByIndex)
  {
    return stats;
  }

  unsigned int device_count = 0;
  if (nvmlDeviceGetCount(&device_count) != NVML_SUCCESS || device_count == 0)
  {
    return stats;
  }

  // Get stats for the first GPU (index 0)
  void* device = nullptr;
  if (nvmlDeviceGetHandleByIndex(0, &device) != NVML_SUCCESS)
  {
    return stats;
  }

  // Temperature
  if (nvmlDeviceGetTemperature)
  {
    unsigned int temp = 0;
    if (nvmlDeviceGetTemperature(device, NVML_TEMPERATURE_GPU, &temp) == NVML_SUCCESS)
    {
      stats[0] = static_cast<double>(temp);
    }
  }

  // GPU utilization
  if (nvmlDeviceGetUtilizationRates)
  {
    nvmlUtilization_t utilization = {0, 0};
    if (nvmlDeviceGetUtilizationRates(device, &utilization) == NVML_SUCCESS)
    {
      stats[1] = static_cast<double>(utilization.gpu);
    }
  }

  // GPU clock
  if (nvmlDeviceGetClockInfo)
  {
    unsigned int clock = 0;
    if (nvmlDeviceGetClockInfo(device, NVML_CLOCK_GRAPHICS, &clock) == NVML_SUCCESS)
    {
      stats[2] = static_cast<double>(clock);
    }
  }

  // Fan speed
  if (nvmlDeviceGetFanSpeed)
  {
    unsigned int fan_speed = 0;
    if (nvmlDeviceGetFanSpeed(device, &fan_speed) == NVML_SUCCESS)
    {
      stats[3] = static_cast<double>(fan_speed);
    }
  }

  return stats;
}

std::vector<std::string> SystemInfoPoller::detect_available_metrics()
{
  std::vector<std::string> metrics;

  // CPU
  double percent = get_cpu_percent();
  if (percent > 0)
    metrics.push_back("cpu_percent");
  double count = static_cast<double>(std::thread::hardware_concurrency());
  if (count > 0)
    metrics.push_back("cpu_count");
  double cpufreq = get_cpu_frequency();
  if (cpufreq > 0)
    metrics.push_back("cpu_freq");
  if (cpu_has_temp())
  {
    double cputemp = get_cpu_temperature();
    if (cputemp > 0 && cputemp < 101)
      metrics.push_back("cpu_temp");
  }

  // Memory
  if (meminfo_available())
  {
    auto meminfo = get_memory_info();
    if (meminfo.first > 0)
      metrics.push_back("mem_percent");
    if (meminfo.second > 0)
      metrics.push_back("mem_used_gb");
  }

  // Disk
  auto diskinfo = get_disk_info();
  if (diskinfo.first > 0)
    metrics.push_back("disk_percent");
  if (diskinfo.second > 0)
    metrics.push_back("disk_free_gb");

  // GPU
  std::string have_amd_gpu = amd_gpu_available();
  if (!have_amd_gpu.empty())
  {
    auto gpustats = get_amd_gpu_stats(have_amd_gpu);
    if (gpustats[0] > 0 && gpustats[0] < 101)
      metrics.push_back("gpu_temp");
    if (gpustats[1] > -1)
      metrics.push_back("gpu_usage");
    if (gpustats[2] > -1)
      metrics.push_back("gpu_clock");
    if (gpustats[3] > -1)
      metrics.push_back("gpu_fan");
  }
  else if (intel_gpu_available())
  {
    metrics.push_back("gpu_temp");
    metrics.push_back("gpu_usage");
    metrics.push_back("gpu_clock");
  }
  else if (nvidia_gpu_available())
  {
    metrics.push_back("gpu_temp");
    metrics.push_back("gpu_usage");
    metrics.push_back("gpu_clock");
    metrics.push_back("gpu_fan");
  }

  return metrics;
}

bool SystemInfoPoller::cpu_has_temp()
{
  return std::filesystem::exists("/sys/class/hwmon");
}

bool SystemInfoPoller::meminfo_available()
{
  return std::filesystem::exists("/proc/meminfo");
}

std::string SystemInfoPoller::amd_gpu_available()
{
  // Check hwmon for amdgpu sensor
  for (int i = 0; i < 10; ++i)
  {
    std::string name_path = "/sys/class/hwmon/hwmon" + std::to_string(i);
    std::ifstream name_file(name_path + "/name");
    if (name_file.is_open())
    {
      std::string sensor_name;
      std::getline(name_file, sensor_name);
      name_file.close();

      if (sensor_name == "amdgpu")
      {
        return name_path;
      }
    }
  }
  return "";
}

bool SystemInfoPoller::intel_gpu_available()
{
  return std::filesystem::exists("/sys/class/drm/card0/gt/gt0");
}

bool SystemInfoPoller::nvidia_gpu_available()
{
  return std::filesystem::exists("/proc/driver/nvidia/version");
}

namespace
{
static libusb_device_handle* _dev = nullptr;

// Private helper
static libusb_device_handle* open_dev(uint16_t vid_want,
                                      uint16_t pid_want,
                                      libusb_context* usbcontext = nullptr)
{
  if (usbcontext == nullptr)
  {
    libusb_init(&usbcontext);
  }
  libusb_device** devs;
  ssize_t cnt = libusb_get_device_list(usbcontext, &devs);
  for (ssize_t i = 0; i < cnt; i++)
  {
    libusb_device_handle* handle;
    libusb_device_descriptor desc;
    libusb_get_device_descriptor(devs[i], &desc);
    if (desc.idVendor == vid_want && desc.idProduct == pid_want)
    {
      libusb_open(devs[i], &handle);
      libusb_free_device_list(devs, 1);
      return handle;
    }
  }
  libusb_free_device_list(devs, 1);
  return nullptr;
}

} // namespace

// Public functions
bool init_dev(uint16_t vid, uint16_t pid)
{
  if (_dev != nullptr)
  {
    try
    {
      libusb_release_interface(_dev, 0);
      libusb_close(_dev);
    }
    catch (...)
    {
    }
  }

  try
  {
    _dev = open_dev(vid, pid);
  }
  catch (...)
  {
    return false;
  }

  libusb_set_auto_detach_kernel_driver(_dev, 1);

  try
  {
    libusb_release_interface(_dev, 0);
  }
  catch (...)
  {
    return false;
  }

  try
  {
    libusb_claim_interface(_dev, 0);
    libusb_reset_device(_dev);
    return true;
  }
  catch (...)
  {
    return false;
  }
}

void cleanup_dev()
{
  if (_dev != nullptr)
  {
    try
    {
      libusb_release_interface(_dev, 0);
      libusb_close(_dev);
      _dev = nullptr;
    }
    catch (...)
    {
    }
  }
}

static void scsi_log(const std::string& msg)
{
  if (!DEBUG)
    return;
  std::lock_guard<std::mutex> lk(scsi_log_mutex);

  static std::ofstream logf("scsi_log.txt", std::ios::app);

  auto now = std::chrono::system_clock::now();
  auto t = std::chrono::system_clock::to_time_t(now);
  auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;

  logf << std::put_time(std::localtime(&t), "%F %T") << "." << std::setw(3) << std::setfill('0')
       << ms.count() << " " << msg << std::endl;
}

void log_sense(const ScsiResult& result)
{
  if (!DEBUG)
    return;
  std::ofstream log("scsi_log.txt", std::ios::app);
  if (result.data.size() >= 14)
  {
    uint8_t key = result.data[2] & 0x0F;
    uint8_t asc = result.data[12];
    uint8_t ascq = result.data[13];
    log << "[SENSE] key=" << (int)key << " ASC=0x" << std::hex << (int)asc << " ASCQ=0x"
        << (int)ascq << std::dec << "\n";
  }
  log.close();
}

static std::string hex_str(uint8_t val)
{
  std::ostringstream oss;
  oss << std::hex << std::setw(2) << std::setfill('0') << (int)val;
  return oss.str();
}

static std::string hex_str(const uint8_t* data, size_t len)
{
  std::ostringstream oss;
  for (size_t i = 0; i < len; ++i)
  {
    oss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(data[i]) << " ";
  }
  return oss.str();
}

bool handshake_with_device()
{
  scsi_log("[HANDSHAKE] Starting full handshake");
  if (!_dev)
  {
    scsi_log("[HANDSHAKE] No device handle");
    return false;
  }

  // Hard-coded endpoints for this device
  constexpr unsigned char EP_OUT = 0x02;
  constexpr unsigned char EP_IN = 0x81;

  // CDBs we use
  const std::vector<uint8_t> tur_cdb(6, 0x00); // TEST UNIT READY
  const std::vector<uint8_t> sense_cdb = {0x03, 0, 0, 0, 18, 0}; // REQUEST SENSE (18)
  const std::vector<uint8_t> mode_cdb = {0x1A, 0, 0, 0, 192, 0}; // MODE SENSE(6) (alloc 192)
  const std::vector<uint8_t> inquiry_cdb = {0x12, 0, 0, 0, 36, 0}; // INQUIRY (alloc 36)

  // vendor CDBs
  std::vector<uint8_t> f5_cdb(16, 0x00);
  f5_cdb[0] = 0xF5; // generic vendor 0xF5 (full-read CDB)

  // APIX probe CDB (16 bytes exactly)
  const std::vector<uint8_t> apix_cdb = {
      0xF5, // opcode
      0x41, 0x50, 0x49, 0x58, // "APIX"
      0xB3, 0x0C, 0x00, 0x00, // observed param (from trace)
      0x00, 0x00, 0x00, 0x00, // padding/reserved
      0x00, 0x00, 0x00 // padding/reserved (total 16 bytes)
  };

  const size_t splash_size = 57627;
  const auto overall_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);

  // ---------------- Stage 1: preconditioning loop ----------------
  while (std::chrono::steady_clock::now() < overall_deadline)
  {
    try
    {
      scsi_log("[HANDSHAKE] Stage 1: TUR");
      ScsiResult tur = send_scsi_command(_dev, tur_cdb, {}, 0);

      if (tur.ok)
      {
        scsi_log("[HANDSHAKE] TUR Good -> Stage 1 satisfied");
        break;
      }

      if (tur.status == 1)
      { // Check Condition
        scsi_log("[HANDSHAKE] TUR Check Condition -> Request Sense");
        ScsiResult sense = send_scsi_command(_dev, sense_cdb, {}, 18);
        if (!sense.data.empty() && sense.data.size() >= 14)
        {
          uint8_t key = sense.data[2] & 0x0F;
          uint8_t asc = sense.data[12];
          uint8_t ascq = sense.data[13];
          scsi_log("[HANDSHAKE] Sense key=" + std::to_string(key) + " ASC=0x" + hex_str(asc) +
                   " ASCQ=0x" + hex_str(ascq));
        }
        else
        {
          scsi_log("[HANDSHAKE] Malformed/empty Request Sense -> resetting "
                   "transport and continuing");
          reset_transport();
        }
      }

      scsi_log("[HANDSHAKE] Stage 1: Mode Sense(6)");
      ScsiResult mode = send_scsi_command(_dev, mode_cdb, {}, 192);
      if (mode.ok)
      {
        scsi_log("[HANDSHAKE] Mode Sense OK -> Stage 1 satisfied");
        break;
      }
      else
      {
        if (mode.status == 1)
        {
          scsi_log("[HANDSHAKE] Mode Sense Check Condition -> Request Sense");
          ScsiResult sense2 = send_scsi_command(_dev, sense_cdb, {}, 18);
          if (sense2.data.size() < 14)
          {
            scsi_log("[HANDSHAKE] Malformed Request Sense after Mode Sense -> "
                     "resetting transport");
            reset_transport();
          }
        }
      }
    }
    catch (const std::exception& e)
    {
      scsi_log(std::string("[HANDSHAKE] Exception in Stage1: ") + e.what());
      reset_transport();
    }

    // small backoff to match Windows probing rhythm
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }

  if (std::chrono::steady_clock::now() >= overall_deadline)
  {
    scsi_log("[HANDSHAKE] Timeout: Stage 1 did not settle");
    return false;
  }

  // ---------------- Stage 2: Inquiry -> APIX probe -> full payload
  // ----------------
  scsi_log("[HANDSHAKE] Stage 2: TUR + Sense + Inquiry + APIX sequence");

  try
  {
    //// TUR first
    // scsi_log("[HANDSHAKE] Sending TUR...");
    // ScsiResult tur = send_scsi_command(_dev, tur_cdb, {}, 0);
    // scsi_log("[HANDSHAKE] TUR ok=" + std::to_string(tur.ok));

    // if (!tur.ok)
    //{
    // scsi_log("[HANDSHAKE] TUR failed, sending Request Sense...");
    // ScsiResult sense = send_scsi_command(_dev, sense_cdb, {}, 18);
    // if (!sense.data.empty() && sense.data.size() >= 14)
    //{
    // uint8_t key = sense.data[2] & 0x0F;
    // uint8_t asc = sense.data[12];
    // uint8_t ascq = sense.data[13];
    // scsi_log("[HANDSHAKE] Sense key=" + std::to_string(key) + " ASC=0x" +
    // hex_str(asc) + " ASCQ=0x" + hex_str(ascq));
    // }
    // }

    std::this_thread::sleep_for(std::chrono::milliseconds(50));

    scsi_log("[HANDSHAKE] Sending Inquiry...");
    ScsiResult inq_res = send_scsi_command(_dev, inquiry_cdb, {}, 36, 0x628bf560);
    scsi_log("[HANDSHAKE] Inquiry ok=" + std::to_string(inq_res.ok) +
             " bytes=" + std::to_string(inq_res.data.size()));

    if (!inq_res.ok || inq_res.data.empty())
    {
      scsi_log("[HANDSHAKE] Inquiry failed");
      return false;
    }
    std::ostringstream oss;
    for (size_t i = 0; i < inq_res.data.size(); i++)
    {
      oss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(inq_res.data[i])
          << " ";
    }
    scsi_log("[HANDSHAKE] Inquiry data: " + oss.str());

    // 2) Send APIX probe (0xF5 with "APIX" payload)
    scsi_log("[HANDSHAKE] Sending APIX probe...");
    ScsiResult apix_res = send_scsi_command(_dev, apix_cdb, {}, 12, 1653339488);
    scsi_log("[HANDSHAKE] APIX ok=" + std::to_string(apix_res.ok) +
             " bytes=" + std::to_string(apix_res.data.size()));
    if (!apix_res.ok)
    {
      scsi_log("[HANDSHAKE] APIX probe failed");
      return false;
    }

    // 3) Request full payload
    scsi_log("[HANDSHAKE] Requesting full payload...");
    ScsiResult full_res = send_scsi_command(_dev, f5_cdb, {}, splash_size, 1653339488);
    scsi_log("[HANDSHAKE] Full payload ok=" + std::to_string(full_res.ok) +
             " bytes=" + std::to_string(full_res.data.size()));
    if (!full_res.ok || full_res.data.empty())
    {
      scsi_log("[HANDSHAKE] Full payload failed");
      return false;
    }

    // 4) Echo payload straight back
    scsi_log("[HANDSHAKE] Echoing payload back, bytes=" + std::to_string(full_res.data.size()));
    ScsiResult echo = send_scsi_command(_dev, f5_cdb, full_res.data, 0, 1653339488);
    if (!echo.ok)
    {
      scsi_log("[HANDSHAKE] Echo failed");
      return false;
    }

    scsi_log("[HANDSHAKE] Stage 2 complete (Inquiry + APIX + full payload + echo)");
    return true;
  }
  catch (const std::exception& e)
  {
    scsi_log(std::string("[HANDSHAKE] Exception in Stage 2: ") + e.what());
    return false;
  }
}

bool device_ready()
{
  // TEST UNIT READY
  std::vector<uint8_t> tur_cdb(6, 0x00);
  auto res = send_scsi_command(_dev, tur_cdb, {}, 0);
  // log_sense(res);

  if (res.ok)
  {
    return true;
  }

  if (res.status == 1)
  { // Check Condition
    // REQUEST SENSE
    std::vector<uint8_t> sense_cdb = {0x03, 0, 0, 0, 18, 0};
    auto sense = send_scsi_command(_dev, sense_cdb, {}, 18);
    // log_sense(sense);

    if (sense.data.size() >= 14)
    {
      uint8_t key = sense.data[2] & 0x0F;
      uint8_t asc = sense.data[12];
      uint8_t ascq = sense.data[13];
    }

    // Perform BOT reset + clear halt (like Windows)
    int rc = libusb_control_transfer(_dev,
                                     0x21, // bmRequestType: Host->Interface | Class | Interface
                                     0xFF, // bRequest: Mass Storage Reset
                                     0, // wValue
                                     0, // wIndex = interface number (store this at init_dev())
                                     0, // wLength
                                     0, 1000);
    if (rc < 0)
    {
    }

    libusb_clear_halt(_dev, 0x81); // bulk IN
    libusb_clear_halt(_dev, 0x02); // bulk OUT
    return false;
  }

  if (res.status == 2)
  { // Phase Error
    libusb_control_transfer(_dev, 0x21, 0xFF, 0, 0, 0, 0, 1000);
    libusb_clear_halt(_dev, 0x81);
    libusb_clear_halt(_dev, 0x02);
    return false;
  }
  return false;
}

void reset_transport()
{
  if (!_dev)
  {
    return;
  }

  // Mass Storage Reset
  int rc = libusb_control_transfer(_dev, 0x21, 0xFF, 0, 0, 0, 0, 1000);
  std::ofstream log("scsi_log.txt", std::ios::app);
  log << "[RESET] Mass Storage Reset rc=" << rc << "\n";

  // Clear halts
  rc = libusb_clear_halt(_dev, 0x81);
  log << "[RESET] clear_halt IN  rc=" << rc << "\n";
  rc = libusb_clear_halt(_dev, 0x02);
  log << "[RESET] clear_halt OUT rc=" << rc << "\n";

  log.close();
}

ScsiResult send_scsi_command(libusb_device_handle* dev,
                             const std::vector<uint8_t>& cdb,
                             const std::vector<uint8_t>& data_out,
                             size_t data_in_len,
                             unsigned int tag)
{
  std::vector<uint8_t> data_in;

  // Build CBW
  std::vector<uint8_t> cbw(31, 0);
  cbw[0] = 'U';
  cbw[1] = 'S';
  cbw[2] = 'B';
  cbw[3] = 'C';

  if (tag == 0)
    tag = TAG++;
  cbw[4] = tag & 0xFF;
  cbw[5] = (tag >> 8) & 0xFF;
  cbw[6] = (tag >> 16) & 0xFF;
  cbw[7] = (tag >> 24) & 0xFF;

  uint32_t data_len = data_in_len ? data_in_len : data_out.size();
  cbw[8] = data_len & 0xFF;
  cbw[9] = (data_len >> 8) & 0xFF;
  cbw[10] = (data_len >> 16) & 0xFF;
  cbw[11] = (data_len >> 24) & 0xFF;

  cbw[12] = data_in_len ? 0x80 : 0x00; // Flags: 0x80 = IN, 0x00 = OUT
  cbw[13] = 0; // LUN
  cbw[14] = static_cast<uint8_t>(cdb.size());

  std::memcpy(cbw.data() + 15, cdb.data(), cdb.size());
  // Convert CBW vector to hex string for logging
  std::string cbw_string;
  for (uint8_t b : cbw)
  {
    char buf[3];
    snprintf(buf, sizeof(buf), "%02x", b);
    cbw_string += buf;
    cbw_string += ' ';
  }
  scsi_log("CBW: " + cbw_string);
  scsi_log("CDB data size is " + std::to_string(cdb.size()));
  // Send CBW
  int transferred = 0;
  int rc = libusb_bulk_transfer(dev, 0x02, cbw.data(), cbw.size(), &transferred, 1000);
  if (rc != 0 || static_cast<size_t>(transferred) != cbw.size())
  {
    ScsiResult blktrans;
    blktrans.ok = false;
    return blktrans;
  }

  // Data phase
  if (data_in_len)
  {
    data_in.resize(data_in_len);
    rc = libusb_bulk_transfer(dev, 0x81, data_in.data(), data_in_len, &transferred, 2000);
    if (rc != 0)
    {
      ScsiResult tmpres; tmpres.ok = false; tmpres.status = 2; return tmpres;
    }
  }
  else if (!data_out.empty())
  {
    rc = libusb_bulk_transfer(dev, 0x02, const_cast<uint8_t*>(data_out.data()), data_out.size(),
                              &transferred, 2000);
    if (rc != 0)
    {
      ScsiResult tmpres; tmpres.ok = false; tmpres.status = 2; return tmpres;
    }
  }
  ScsiResult result;
  result.data = std::move(data_in);

  // CSW
  std::vector<uint8_t> csw(13);
  rc = libusb_bulk_transfer(dev, 0x81, csw.data(), csw.size(), &transferred, 1000);
  if (rc != 0 || transferred != 13 || std::memcmp(csw.data(), "USBS", 4) != 0)
  {
    result.status = 2; // Phase Error
    result.ok = false;
    {
      static std::mutex log_mutex;
      std::lock_guard<std::mutex> lock(log_mutex);
      if (DEBUG)
      {
        std::ofstream log("scsi_log.txt", std::ios::app);

        log << "[SCSI] CDB: ";
        for (auto b : cdb)
          log << std::hex << std::setw(2) << std::setfill('0') << (int)b << " ";
        log << " | CSW invalid (rc=" << rc << " transferred=" << transferred << ")\n";

        log.close();
      }
    }

    return result;
  }

  // Parse CSW
  result.status = csw[12];
  result.ok = (result.status == 0);
  result.data = std::move(data_in);

  static std::mutex log_mutex; // protect logfile if called from multiple threads

  std::lock_guard<std::mutex> lock(log_mutex);
  if (DEBUG)
  {
    std::ofstream log("scsi_log.txt", std::ios::app);

    log << "[SCSI] CDB: ";
    for (auto b : cdb)
      log << std::hex << std::setw(2) << std::setfill('0') << (int)b << " ";

    log << " | Status=" << std::dec << (int)result.status << " ok=" << result.ok
        << " DataIn=" << result.data.size() << " bytes\n";

    // If it was REQUEST SENSE and data is long enough, decode ASC/ASCQ
    if (!cdb.empty() && cdb[0] == 0x03 && result.data.size() >= 14)
    {
      uint8_t key = result.data[2] & 0x0F;
      uint8_t asc = result.data[12];
      uint8_t ascq = result.data[13];
      log << "  [SENSE] key=" << (int)key << " ASC=0x" << std::hex << (int)asc << " ASCQ=0x"
          << (int)ascq << std::dec << "\n";
    }

    log.close();
  }

  return result;
}

bool update_lcd_image(const uint8_t* pil_img, libusb_device_handle* dev)
{
  if (dev == nullptr)
  {
    dev = _dev;
  }
  if (dev == nullptr)
  {
    return false;
  }

  // Convert to chunks of RGB565
  auto chunks = ImageConverter::image_to_rgb565_chunks(pil_img);

  for (size_t idx = 0; idx < chunks.size(); ++idx)
  {
    std::vector<uint8_t> cdb(16, 0);
    cdb[0] = 0xF5; // Vendor command
    cdb[1] = 0x01;
    cdb[2] = 0x01;
    cdb[3] = static_cast<uint8_t>(idx);

    uint32_t length = static_cast<uint32_t>(chunks[idx].size());
    // Write length in little-endian
    cdb[12] = (length) & 0xFF;
    cdb[13] = (length >> 8) & 0xFF;
    cdb[14] = (length >> 16) & 0xFF;
    cdb[15] = (length >> 24) & 0xFF;

    {
      ScsiResult res = send_scsi_command(dev, cdb, chunks[idx]);
      if (!res.ok) {
        // USB transfer failed for this chunk — signal failure to caller
        return false;
      }
    }
  }
    // All chunks sent successfully
    return true;
}

// --- ImageConverter ---
static inline uint16_t rgb_to_rgb565(uint8_t r, uint8_t g, uint8_t b)
{
  return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

std::array<std::vector<uint8_t>, 3> ImageConverter::image_to_rgb565_chunks(
    const uint8_t* image_data)
{
  std::array<std::vector<uint8_t>, 3> chunks;
  std::array<int, 3> chunk_widths = {120, 120, 80};
  int start = 0;

  for (size_t i = 0; i < chunk_widths.size(); ++i)
  {
    int w = chunk_widths[i];
    chunks[i].reserve(w * HEIGHT * 2); // preallocate
    for (int col = 0; col < w; ++col)
    {
      int ac = start + col;
      for (int row = 0; row < HEIGHT; ++row)
      {
        int flipped = HEIGHT - 1 - row;
        int idx = (flipped * WIDTH + ac) * 3; // RGB stride
        uint8_t r = image_data[idx + 0];
        uint8_t g = image_data[idx + 1];
        uint8_t b = image_data[idx + 2];

        uint16_t rgb565 = rgb_to_rgb565(r, g, b);
        chunks[i].push_back(static_cast<uint8_t>(rgb565 & 0xFF));
        chunks[i].push_back(static_cast<uint8_t>((rgb565 >> 8) & 0xFF));
      }
    }
    start += w;
  }

  return chunks;
}

void BackgroundManager::set_background_paths(const std::string& image, const std::string& video)
{
  image_path = image;
  video_path = video;
}

cv::Mat BackgroundManager::create_default_background()
{
  if (default_bg.empty())
  {
    default_bg = cv::Mat(240, 320, CV_8UC3);
    for (int y = 0; y < 240; ++y)
    {
      // Use floating point for smoother gradient
      double ratio = y / 240.0;
      int val = static_cast<int>(20 + ratio * 40);

      // Add slight noise/dithering to break up banding
      int noise = (y % 3) - 1; // -1, 0, or 1
      val = std::max(0, std::min(255, val + noise));

      cv::line(default_bg, cv::Point(0, y), cv::Point(320, y), cv::Scalar(val, val / 2, val));
    }
  }
  return default_bg.clone();
}

cv::Mat BackgroundManager::load_static_background(const std::string& background_path)
{
  if (background_path.empty() || !std::filesystem::exists(background_path))
  {
    return cv::Mat();
  }
  std::time_t current_mtime =
      std::filesystem::last_write_time(background_path).time_since_epoch().count();

  if (static_bg.empty() || static_bg_path != background_path || static_bg_mtime != current_mtime)
  {
    try
    {
      cv::Mat img = cv::imread(background_path, cv::IMREAD_UNCHANGED);
      if (img.empty())
      {
        return cv::Mat();
      }
      has_alpha = (img.channels() == 4);

      cv::resize(img, img, cv::Size(320, 240));
      static_bg = img;
      static_bg_path = background_path;
      static_bg_mtime = current_mtime;
    }
    catch (const std::exception& e)
    {
      return cv::Mat();
    }
  }
  return static_bg.clone();
}

cv::Mat BackgroundManager::get_background(const std::string& video_path,
                                          const std::string& image_path)
{
  cv::Mat img, vid;

  // --- 1️⃣ Load static image (if configured) ---
  if (!image_path.empty())
  {
    img = load_static_background(image_path);
    //has_alpha = (img.channels() == 4);
  }

  // --- 2️⃣ Load or update video background (if configured) ---
  if (!video_path.empty())
  {
    std::string ext = std::filesystem::path(video_path).extension().string();
    std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);

    if (ext == ".mp4" || ext == ".avi" || ext == ".mov" || ext == ".mkv")
    {
      if (!video_bg || video_bg->get_path() != video_path)
      {
        if (video_bg)
          video_bg->stop();

        video_bg = std::make_unique<VideoBackground>(video_path, "loop", 24);
        video_bg->start_playback();
      }
      vid = video_bg->get_current_frame();
    }
  }

  // --- 3️⃣ Combined content (image + video) ---
  if (!img.empty() && !vid.empty())
  {
    if (vid.size() != img.size())
      cv::resize(vid, vid, img.size());
    if (has_alpha)
      return compose_with_video(img, vid);
    else
      return img; // image overrides but no alpha blending
  }

  // --- 4️⃣ Video only ---
  if (!vid.empty())
    return vid;

  // --- 5️⃣ Static only ---
  if (!img.empty())
    return img;

  // --- 6️⃣ Fallback ---
  return create_default_background();
}

cv::Mat BackgroundManager::compose_with_video(const cv::Mat& argb_image, const cv::Mat& video_frame)
{
  if (argb_image.empty() || video_frame.empty())
    return argb_image;

  // --- Ensure same size ---
  cv::Mat resized_video;
  if (video_frame.size() != argb_image.size())
    cv::resize(video_frame, resized_video, argb_image.size());
  else
    resized_video = video_frame;

  // --- Split alpha ---
  std::vector<cv::Mat> channels;
  cv::split(argb_image, channels); // B, G, R, A
  cv::Mat alpha = channels[3];

  // --- Extract BGR (drop alpha) ---
  cv::Mat fg_bgr;
  cv::merge(std::vector<cv::Mat>{channels[0], channels[1], channels[2]}, fg_bgr);

  // --- Convert to float and normalize ---
  cv::Mat fg_f, bg_f, alpha_f;
  fg_bgr.convertTo(fg_f, CV_32FC3, 1.0 / 255.0);
  resized_video.convertTo(bg_f, CV_32FC3, 1.0 / 255.0);
  alpha.convertTo(alpha_f, CV_32FC1, 1.0 / 255.0);

  // --- Expand alpha to 3 channels ---
  cv::Mat alpha_3c;
  cv::merge(std::vector<cv::Mat>{alpha_f, alpha_f, alpha_f}, alpha_3c);

  // --- Blend in BGR space ---
  cv::Mat inv_alpha_3c;
  cv::subtract(cv::Scalar(1.0, 1.0, 1.0), alpha_3c, inv_alpha_3c);
  cv::Mat blended_f = fg_f.mul(alpha_3c) + bg_f.mul(inv_alpha_3c);

  // --- Convert back to 8-bit BGRA ---
  cv::Mat blended_bgr, blended_bgra;
  blended_f.convertTo(blended_bgr, CV_8UC3, 255.0);
  cv::cvtColor(blended_bgr, blended_bgra, cv::COLOR_BGR2BGRA);

  // --- Set full alpha ---
  std::vector<cv::Mat> final_channels;
  cv::split(blended_bgra, final_channels);
  final_channels[3] = cv::Mat(argb_image.size(), CV_8UC1, cv::Scalar(255));
  cv::merge(final_channels, blended_bgra);

  return blended_bgra;
}

std::vector<uint8_t> BackgroundManager::get_background_bytes(const std::string& video_path,
                                                             const std::string& image_path)
{
  cv::Mat bg = get_background(video_path, image_path);
  if (bg.empty())
  {
    return std::vector<uint8_t>();
  }

  cv::Mat bytes_mat;

  // Convert static BGR image to RGB
  cv::cvtColor(bg, bytes_mat, cv::COLOR_BGRA2RGB);

  // Convert to raw bytes (same as PIL's .tobytes())
  std::vector<uint8_t> bytes;
  bytes.assign(bytes_mat.datastart, bytes_mat.dataend);
  return bytes;
}

BackgroundManager& get_background_manager()
{
  return bg_manager;
}

void VideoBackground::start_playback()
{
  if (_playing)
    return;
  if (!_streaming && _frames.empty())
    return;

  _playing = true;
  _thread = std::thread(&VideoBackground::_play_loop, this);
}

void VideoBackground::stop()
{
  _playing = false;
  if (_thread.joinable())
  {
    _thread.join();
  }
  if (_streaming && cap.isOpened())
  {
    cap.release();
  }
}

void VideoBackground::_init()
{
  cap.open(path);
  if (!cap.isOpened())
  {
    return;
  }

  int total_frames = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_COUNT));
  double fps = cap.get(cv::CAP_PROP_FPS);
  double duration_sec = (fps > 0) ? total_frames / fps : 0;

  if (duration_sec > 10.0)
  {
    // Stream mode
    _streaming = true;
    _fps = (fps > 0) ? static_cast<int>(fps) : _fps;
  }
  else
  {
    // Preload mode
    _preload_frames();
    _streaming = false;
  }
}

cv::Mat VideoBackground::get_current_frame()
{
  std::lock_guard<std::mutex> lock(_lock);
  if (_streaming)
  {
    return _current_frame.clone();
  }
  else if (!_frames.empty())
  {
    return _frames[_frame_index].clone();
  }
  return cv::Mat();
}

bool VideoBackground::is_loaded() const
{
  return _streaming || !_frames.empty();
}

size_t VideoBackground::get_frame_count() const
{
  return _frames.size();
}

void VideoBackground::_preload_frames()
{
  cv::Mat frame;
  while (cap.read(frame))
  {
    if (frame.empty())
      break;
    cv::Mat resized;
    cv::resize(frame, resized, cv::Size(320, 240), 0, 0, cv::INTER_LANCZOS4);
    _frames.push_back(resized.clone());
  }
  cap.release();
}

void VideoBackground::_play_loop()
{
  if (_streaming)
  {
    _stream_loop();
  }
  else
  {
    _preloaded_loop();
  }
}

void VideoBackground::_stream_loop()
{
  double fps = cap.get(cv::CAP_PROP_FPS);
  int delay = (fps > 0) ? static_cast<int>(1000.0 / fps) : 41;

  cv::Mat frame;
  while (_playing)
  {
    if (!cap.read(frame) || frame.empty())
    {
      cap.set(cv::CAP_PROP_POS_FRAMES, 0); // loop
      continue;
    }

    cv::Mat resized;
    cv::resize(frame, resized, cv::Size(320, 240), 0, 0, cv::INTER_LANCZOS4);

    {
      std::lock_guard<std::mutex> lock(_lock);
      _current_frame = resized.clone();
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(delay));
  }
}

void VideoBackground::_preloaded_loop()
{
  while (_playing && !_frames.empty())
  {
    {
      std::lock_guard<std::mutex> lock(_lock);
      if (mode == "loop")
      {
        _frame_index = (_frame_index + 1) % _frames.size();
      }
      else if (mode == "bounce")
      {
        if (_forward)
        {
          _frame_index++;
          if (_frame_index >= _frames.size() - 1)
            _forward = false;
        }
        else
        {
          if (_frame_index > 0)
            _frame_index--;
          if (_frame_index <= 0)
            _forward = true;
        }
      }
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1000 / _fps));
  }
}

ConfigManager::ConfigManager(const std::string& path) : _path(path)
{
}

bool ConfigManager::load_config_from_defaults()
{
  // Clear existing data and set up defaults
  _data.clear();

  // Time configuration
  _data["time"] = {{"x", 60},
                   {"y", 5},
                   {"font", {{"family", "DejaVu Sans"}, {"size", 38}, {"style", "bold"}}},
                   {"color", "#FFFFFF"},
                   {"enabled", true},
                   {"format", "12h"}};

  // Date configuration
  _data["date"] = {{"x", 85},
                   {"y", 60},
                   {"font", {{"family", "DejaVu Sans"}, {"size", 24}, {"style", "bold"}}},
                   {"color", "#CCCCCC"},
                   {"enabled", true},
                   {"format", "%d-%m-%Y"}};

  // Custom text configuration
  _data["custom"] = {{"x", 90},
                     {"y", 90},
                     {"font", {{"family", "DejaVu Sans"}, {"size", 38}, {"style", "bold"}}},
                     {"color", "#00FF00"},
                     {"enabled", false},
                     {"text", "LINUX"}};

  // CPU label configuration
  _data["cpu_label"] = {{"x", 15},
                        {"y", 140},
                        {"font", {{"family", "DejaVu Sans"}, {"size", 20}, {"style", "bold"}}},
                        {"color", "#FF6B35"},
                        {"enabled", true},
                        {"text", "CPU"}};

  // GPU label configuration
  _data["gpu_label"] = {{"x", 15},
                        {"y", 180},
                        {"font", {{"family", "DejaVu Sans"}, {"size", 20}, {"style", "bold"}}},
                        {"color", "#35A7FF"},
                        {"enabled", true},
                        {"text", "GPU"}};

  // Add module defaults (M1..M6)
  addDefaultModules();

  return true;
}

void ConfigManager::addDefaultModules()
{
  // M1 - CPU Temperature
  _data["M1"] = {{"metric", "cpu_temp"},
                 {"enabled", true},
                 {"font", {{"family", "DejaVu Sans"}, {"size", 20}, {"style", "bold"}}},
                 {"color", "#FF6B35"},
                 {"x", 70},
                 {"y", 140}};

  // M2 - CPU Frequency
  _data["M2"] = {{"metric", "cpu_percent"},
                 {"enabled", true},
                 {"font", {{"family", "DejaVu Sans"}, {"size", 20}, {"style", "bold"}}},
                 {"color", "#FF6B35"},
                 {"x", 135},
                 {"y", 140}};

  // M3 - CPU Percentage
  _data["M3"] = {{"metric", "cpu_freq"},
                 {"enabled", true},
                 {"font", {{"family", "DejaVu Sans"}, {"size", 20}, {"style", "bold"}}},
                 {"color", "#FF6B35"},
                 {"x", 195},
                 {"y", 140}};

  // M4 - GPU Temperature
  _data["M4"] = {{"metric", "gpu_temp"},
                 {"enabled", true},
                 {"font", {{"family", "DejaVu Sans"}, {"size", 20}, {"style", "bold"}}},
                 {"color", "#35A7FF"},
                 {"x", 70},
                 {"y", 180}};

  // M5 - GPU Clock
  _data["M5"] = {{"metric", "gpu_usage"},
                 {"enabled", true},
                 {"font", {{"family", "DejaVu Sans"}, {"size", 20}, {"style", "bold"}}},
                 {"color", "#35A7FF"},
                 {"x", 135},
                 {"y", 180}};

  // M6 - GPU Usage
  _data["M6"] = {{"metric", "gpu_clock"},
                 {"enabled", true},
                 {"font", {{"family", "DejaVu Sans"}, {"size", 20}, {"style", "bold"}}},
                 {"color", "#35A7FF"},
                 {"x", 195},
                 {"y", 180}};
}

bool ConfigManager::load_config(const std::string& path)
{
  // Start fresh from defaults (like Python version)
  load_config_from_defaults();

  // Try to load from file if it exists
  std::ifstream f(path);
  if (f.is_open())
  {
    try
    {
      nlohmann::json loaded_config;
      f >> loaded_config;

      // Merge loaded config with defaults (update existing keys)
      _data.update(loaded_config);

      return true;
    }
    catch (const std::exception& e)
    {
      return false;
    }
  }

  // Return true even if file doesn't exist (using defaults)
  return true;
}

bool ConfigManager::save_config(const std::string& path) const
{
  std::ofstream f(path);
  if (!f)
    return false;
  f << _data.dump(4);
  return true;
}

std::string ConfigManager::dump(int indent) const
{
  return _data.dump(indent);
}

// Dotted-key lookup
nlohmann::json ConfigManager::get_value(const std::string& key) const
{
  std::istringstream ss(key);
  std::string part;
  const nlohmann::json* current = &_data;
  while (std::getline(ss, part, '.'))
  {
    if (!current->contains(part))
      return nullptr;
    current = &((*current)[part]);
  }
  return *current;
}

void ConfigManager::set_value(const std::string& key, const nlohmann::json& value)
{
  std::istringstream ss(key);
  std::string part;
  nlohmann::json* current = &_data;
  std::vector<std::string> parts;

  while (std::getline(ss, part, '.'))
  {
    parts.push_back(part);
  }

  for (size_t i = 0; i < parts.size(); ++i)
  {
    const auto& p = parts[i];
    if (i == parts.size() - 1)
    {
      (*current)[p] = value;
    }
    else
    {
      if (!(*current).contains(p) || !(*current)[p].is_object())
      {
        (*current)[p] = nlohmann::json::object();
      }
      current = &((*current)[p]);
    }
  }
}

void ConfigManager::update_config_value(const std::string& key, const nlohmann::json& value)
{
  set_value(key, value);
}
