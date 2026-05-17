#include <pybind11/pybind11.h>
#include <pybind11_json.hpp>
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

    m.def("init_dev", &init_dev);
    m.def("cleanup_dev", &cleanup_dev);
    m.def("device_ready", &device_ready);
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
         py::arg("image_path") = "")

    .def("update_overlay_rgba", [](BackgroundManager &mgr, const std::string &tag, py::buffer buf, int w, int h, int x, int y){
         py::buffer_info info = buf.request();
         const uint8_t* data_ptr = static_cast<const uint8_t*>(info.ptr);
         mgr.update_overlay_rgba(tag, data_ptr, w, h, x, y);
    })
    .def("start_lcd_stream", &BackgroundManager::start_lcd_stream, py::arg("video_path") = "", py::arg("image_path") = "")
    .def("stop_lcd_stream", &BackgroundManager::stop_lcd_stream)
    .def("get_last_frame_bytes", [](BackgroundManager &mgr){
         auto vec = mgr.get_last_frame_bytes_vec();
         if (vec.empty()) return py::bytes();
         return py::bytes(reinterpret_cast<const char*>(vec.data()), vec.size());
    })
    .def("set_error_callback", [](BackgroundManager &mgr, py::function cb){
         mgr.set_error_callback([cb](const std::string &msg){
             py::gil_scoped_acquire acquire;
             try { cb(msg); } catch(const py::error_already_set &e) {
                 std::cerr << "Python callback exception: " << e.what() << std::endl;
             }
         });
    })
    // =================================================================
    // NEW: Overwrite the callback with a capture-less dummy lambda
    // =================================================================
    .def("clear_error_callback", [](BackgroundManager &mgr){
         mgr.set_error_callback([](const std::string &msg){
             // Intentionally empty. Captures zero Python references!
         });
    })
    ;

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

