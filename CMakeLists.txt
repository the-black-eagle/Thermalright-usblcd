cmake_minimum_required(VERSION 3.16)
project(lcd_driver LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

# --- Fetch pybind11
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v2.12.0   # choose latest stable release
)
FetchContent_MakeAvailable(pybind11)

# --- Fetch nlohmann/json (optional but nice for portability)
FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(nlohmann_json)

find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(OpenCV REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(LIBUSB REQUIRED libusb-1.0)

# --- Backend driver (C++ sources in src/)
set(SRC_DIR ${CMAKE_SOURCE_DIR}/src)
pybind11_add_module(lcd_driver
    ${SRC_DIR}/CLcdDriver.cpp
    ${SRC_DIR}/bindings.cpp
)

target_include_directories(lcd_driver PRIVATE
    ${SRC_DIR}
    ${LIBUSB_INCLUDE_DIRS}
    ${OpenCV_INCLUDE_DIRS}
)

target_link_libraries(lcd_driver PRIVATE
    ${LIBUSB_LIBRARIES}
    ${OpenCV_LIBS}
    nlohmann_json::nlohmann_json
)

# --- Copy Python frontend (from python/ → build/)
set(PYTHON_DIR ${CMAKE_SOURCE_DIR}/python)
configure_file(
    ${PYTHON_DIR}/gui_controller.py
    ${CMAKE_CURRENT_BINARY_DIR}/gui_controller.py
    COPYONLY
)

# --- Run target
add_custom_target(run
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_BINARY_DIR}/gui_controller.py
    DEPENDS lcd_driver
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    COMMENT "Running LCD GUI controller..."
)
