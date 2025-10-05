cmake_minimum_required(VERSION 3.16)
project(lcd_driver LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

# --- pybind11
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v2.12.0
)
FetchContent_MakeAvailable(pybind11)

# --- nlohmann/json
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

set(SRC_DIR ${CMAKE_SOURCE_DIR}/src)
set(PYTHON_DIR ${CMAKE_SOURCE_DIR}/python)

# --- Build backend module
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

# --- Install the Python frontend (used for local testing)
configure_file(
    ${PYTHON_DIR}/gui_controller.py
    ${CMAKE_CURRENT_BINARY_DIR}/gui_controller.py
    COPYONLY
)

# --- Custom target: build AppImage
add_custom_target(appimage ALL
    COMMENT "Packaging LCD Controller into AppImage"
)

add_custom_command(TARGET appimage POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Building AppImage..."

    # Prepare directories
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/applications
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/icons/hicolor/256x256/apps

    # Copy files
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_CURRENT_BINARY_DIR}/gui_controller.py ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin/gui_controller.py
    # Find the built Python extension (.so)
    COMMAND ${CMAKE_COMMAND} -E echo "Locating built lcd_driver module..."
    COMMAND ${CMAKE_COMMAND} -DSEARCH_DIR=${CMAKE_CURRENT_BINARY_DIR} -DDEST_DIR=${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin -P ${CMAKE_SOURCE_DIR}/cmake/copy_driver.cmake
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_SOURCE_DIR}/tr-driver.png ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/icons/hicolor/256x256/apps/tr-driver.png
    # Write .desktop file using CMake script mode
    COMMAND ${CMAKE_COMMAND} -DOUTPUT=${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/applications/tr-driver.desktop
                             -P ${CMAKE_SOURCE_DIR}/cmake/write_desktop.cmake

    # Bundle Python using PyInstaller
    COMMAND ${Python3_EXECUTABLE} -m pip install pyinstaller --upgrade
    COMMAND ${Python3_EXECUTABLE} -m PyInstaller --onefile --name gui_controller --hidden-import=PIL._tkinter_finder --hidden-import=PIL._imagingtk --hidden-import=PIL.ImageTk
    ${CMAKE_CURRENT_BINARY_DIR}/gui_controller.py
    # Copy the binary into AppDir
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_CURRENT_BINARY_DIR}/dist/gui_controller ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin/gui_controller

    # Build the AppImage
    COMMAND appimagetool ${CMAKE_CURRENT_BINARY_DIR}/AppDir ${CMAKE_CURRENT_BINARY_DIR}/LCD_Controller-x86_64.AppImage

    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)

# --- Run target for local testing
add_custom_target(run
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_BINARY_DIR}/gui_controller.py
    DEPENDS lcd_driver
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    COMMENT "Running LCD GUI controller..."
)
