#include <pybind11/pybind11.h>
#include <pybind11_json.hpp>
#include <pybind11_json/pybind11_json.hpp>
#include <pybind11/stl.h>
#include "CLcdDriver.h"

namespace py = pybind11;

PYBIND11_MODULE(lcd_driver, m) {
    py::class_<SystemInfoPoller>(m, "CSystemInfoPoller", py::module_local())
        .def(py::init<>())
        .def("start", &SystemInfoPoller::start)
        .def("stop", &SystemInfoPoller::stop)
        .def("get_info", &SystemInfoPoller::get_info)
        .def("get_available_metrics", &SystemInfoPoller::get_available_metrics);

    m.def("init_dev", &init_dev, py::arg("vid") = 0x0402, py::arg("pid") = 0x3922);
    m.def("cleanup_dev", &cleanup_dev);
    m.def("device_ready", &device_ready);
    m.def("reset_transport", &reset_transport);
    m.def("handshake_with_device", &handshake_with_device);
    
    py::class_<ConfigManager>(m, "ConfigManager")
        .def(py::init<const std::string&>())
        .def("load_config", &ConfigManager::load_config)
        .def("get_config", &ConfigManager::get_config)
        .def("load_config_from_defaults", &ConfigManager::load_config_from_defaults)
        .def("update_config_value", &ConfigManager::update_config_value)
        .def("save_config", &ConfigManager::save_config);


    py::class_<ImageConverter>(m, "ImageConverter")
        .def_static("image_to_rgb565_chunks", &ImageConverter::image_to_rgb565_chunks);
        
    py::class_<BackgroundManager>(m, "BackgroundManager")
    .def("get_background_bytes",
         [](BackgroundManager &self,
            const std::string &video_path,
            const std::string &image_path)
         {
             auto vec = self.get_background_bytes(video_path, image_path);
             return py::bytes(reinterpret_cast<const char *>(vec.data()),
                              vec.size());
         },
         py::arg("video_path") = "",
         py::arg("image_path") = "");


    m.def("get_background_manager", &get_background_manager, 
        py::return_value_policy::reference);

    // Bind update_lcd_image
    m.def("update_lcd_image", [](py::buffer buf) {
        py::buffer_info info = buf.request();
        if (info.ndim != 1)
            throw std::runtime_error("Expected a 1D contiguous buffer");
        const uint8_t* data_ptr = static_cast<const uint8_t*>(info.ptr);
        return update_lcd_image(data_ptr); // default dev is nullptr
    });
}

