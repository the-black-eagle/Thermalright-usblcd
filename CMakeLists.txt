cmake_minimum_required(VERSION 3.16)
project(tr_driver LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- Extract version from debian/changelog ---
execute_process(
    COMMAND bash -c "head -n1 ${CMAKE_SOURCE_DIR}/debian/changelog | awk '{print $2}' | tr -d '()'"
    OUTPUT_VARIABLE APP_VERSION
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
message(STATUS "Detected version from changelog: ${APP_VERSION}")

# --- Dependencies
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(OpenCV REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(LIBUSB REQUIRED libusb-1.0)
find_package(pybind11 REQUIRED)
find_package(nlohmann_json REQUIRED)

# Try to find pybind11_json header
find_path(PYBIND11_JSON_INCLUDE_DIR
    NAMES pybind11_json/pybind11_json.hpp pybind11_json.hpp
    PATHS
        /usr/include
        /usr/local/include
        ${CMAKE_SOURCE_DIR}/include
    PATH_SUFFIXES pybind11_json
)

if(PYBIND11_JSON_INCLUDE_DIR)
    message(STATUS "Found pybind11_json: ${PYBIND11_JSON_INCLUDE_DIR}")
else()
    message(WARNING "pybind11_json not found - build may fail")
endif()

set(SRC_DIR ${CMAKE_SOURCE_DIR}/src)
set(PYTHON_DIR ${CMAKE_SOURCE_DIR}/python)
set(DATA_DIR ${CMAKE_SOURCE_DIR}/USBLCD)
set(APP_NAME tr-driver)
set(APP_ICON ${CMAKE_SOURCE_DIR}/${APP_NAME}.png)
set(APP_DESKTOP ${CMAKE_SOURCE_DIR}/cmake/write_desktop.cmake)
set(APP_RUN ${CMAKE_SOURCE_DIR}/cmake/AppRun.in)

# --- Backend module
pybind11_add_module(lcd_driver
    ${SRC_DIR}/CLcdDriver.cpp
    ${SRC_DIR}/bindings.cpp
)

target_include_directories(lcd_driver PRIVATE
    ${SRC_DIR}
    ${LIBUSB_INCLUDE_DIRS}
    ${OpenCV_INCLUDE_DIRS}
    ${PYBIND11_JSON_INCLUDE_DIR}
)

target_link_libraries(lcd_driver PRIVATE
    ${LIBUSB_LIBRARIES}
    ${OpenCV_LIBS}
    nlohmann_json::nlohmann_json
)

# Install the compiled backend
install(TARGETS lcd_driver LIBRARY DESTINATION lib)

# Install Python modules
install(PROGRAMS ${PYTHON_DIR}/gui_controller.py DESTINATION lib/tr-driver RENAME tr-driver)
install(FILES ${PYTHON_DIR}/background_selector.py DESTINATION lib/tr-driver)

# Install data files (themes and videos)
install(DIRECTORY ${DATA_DIR}/
        DESTINATION share/tr-driver/USBLCD
        FILES_MATCHING 
        PATTERN "*.png"
        PATTERN "*.mp4"
        PATTERN "*.avi"
        PATTERN "*.mov"
        PATTERN "*.mkv"
        PATTERN "*.json")

# Add a small system-wide launcher
install(CODE "
file(WRITE \"\${CMAKE_INSTALL_PREFIX}/bin/tr-driver\" 
\"#!/usr/bin/env bash\\nexec python3 /lib/tr-driver/tr-driver \\\"\\$@\\\"\\n\")
file(CHMOD \"\${CMAKE_INSTALL_PREFIX}/bin/tr-driver\" PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
")

# Desktop entry
install(CODE "
file(WRITE \"\${CMAKE_INSTALL_PREFIX}/share/applications/tr-driver.desktop\" 
\"[Desktop Entry]\\nType=Application\\nName=LCD System Monitor\\nExec=tr-driver\\nIcon=tr-driver\\nTerminal=false\\nCategories=Utility;System;\\n\")
")

# Icon
install(FILES ${APP_ICON} DESTINATION share/icons/hicolor/256x256/apps)


# ===============================================================
# Custom Targets
# ===============================================================

# --- 1️⃣ driver: build only the C++ backend
add_custom_target(driver
    DEPENDS lcd_driver
    COMMENT "Building C++ backend only (lcd_driver.so)"
)

# --- 2️⃣ test: build backend, copy Python GUI, and run
add_custom_target(lcd_test
    COMMAND ${CMAKE_COMMAND} -E copy ${PYTHON_DIR}/gui_controller.py ${CMAKE_CURRENT_BINARY_DIR}/gui_controller.py
    COMMAND ${CMAKE_COMMAND} -E copy ${PYTHON_DIR}/background_selector.py ${CMAKE_CURRENT_BINARY_DIR}/background_selector.py
    COMMAND ${CMAKE_COMMAND} -E copy ${PYTHON_DIR}/themed_messagebox.py ${CMAKE_CURRENT_BINARY_DIR}/themed_messagebox.py

    # Create symlink to USBLCD in build directory for development
    COMMAND ${CMAKE_COMMAND} -E create_symlink ${DATA_DIR} ${CMAKE_CURRENT_BINARY_DIR}/USBLCD
    
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_BINARY_DIR}/gui_controller.py
    DEPENDS lcd_driver
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    COMMENT "Running LCD GUI with built backend..."
    EXCLUDE_FROM_ALL
)

# --- 3️⃣ appimage: build and package AppImage
add_custom_target(appimage
    COMMENT "Building ${APP_NAME}.AppImage..."
)

add_custom_command(TARGET appimage POST_BUILD
    # Ensure driver is built first
    COMMAND ${CMAKE_COMMAND} -E echo "Locating built lcd_driver module..."
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/lib
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/applications
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/icons/hicolor/256x256/apps
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/tr-driver

    # Copy Python modules + backend
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_CURRENT_BINARY_DIR}/lcd_driver*.so ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/lib/
    COMMAND ${CMAKE_COMMAND} -E copy ${PYTHON_DIR}/gui_controller.py ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin/gui_controller.py
    COMMAND ${CMAKE_COMMAND} -E copy ${PYTHON_DIR}/background_selector.py ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin/background_selector.py
    COMMAND ${CMAKE_COMMAND} -E copy ${PYTHON_DIR}/themed_messagebox.py ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin/themed_messagebox.py

    # Copy USBLCD data directory
    COMMAND ${CMAKE_COMMAND} -E copy_directory ${DATA_DIR} ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/tr-driver/USBLCD

    # Copy desktop file to BOTH locations (usr/share/applications AND AppDir root)
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_SOURCE_DIR}/tr-driver.desktop ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/applications/${APP_NAME}.desktop
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_SOURCE_DIR}/tr-driver.desktop ${CMAKE_CURRENT_BINARY_DIR}/AppDir/${APP_NAME}.desktop
    
    # Copy icon to multiple locations
    COMMAND ${CMAKE_COMMAND} -E copy ${APP_ICON} ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png
    COMMAND ${CMAKE_COMMAND} -E copy ${APP_ICON} ${CMAKE_CURRENT_BINARY_DIR}/AppDir/${APP_NAME}.png
    
    # Copy and make AppRun executable
    COMMAND ${CMAKE_COMMAND} -E copy ${APP_RUN} ${CMAKE_CURRENT_BINARY_DIR}/AppDir/AppRun
    COMMAND chmod +x ${CMAKE_CURRENT_BINARY_DIR}/AppDir/AppRun

    # Bundle Python using PyInstaller
    COMMAND ${Python3_EXECUTABLE} -m pip install pyinstaller --upgrade
    COMMAND ${Python3_EXECUTABLE} -m PyInstaller --onefile --name ${APP_NAME} --icon=${APP_ICON} 
            --add-data "${DATA_DIR}:USBLCD"
            --hidden-import=PIL._tkinter_finder --hidden-import=PIL._imagingtk --hidden-import=PIL.ImageTk --hidden-import=tkinter --hidden-import=pystray
            ${CMAKE_SOURCE_DIR}/python/gui_controller.py

    # Copy frozen binary to AppDir
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_CURRENT_BINARY_DIR}/dist/${APP_NAME} ${CMAKE_CURRENT_BINARY_DIR}/AppDir/usr/bin/${APP_NAME}

    # Build final AppImage with versioned name
    COMMAND appimagetool
        ${CMAKE_CURRENT_BINARY_DIR}/AppDir
        ${CMAKE_CURRENT_BINARY_DIR}/${APP_NAME}-${APP_VERSION}-x86_64.AppImage
    EXCLUDE_FROM_ALL
)
add_dependencies(appimage lcd_driver)

# --- 4️⃣ deb: prepare staging area for Debian package
add_custom_target(deb
    COMMAND ${CMAKE_COMMAND} --install ${CMAKE_BINARY_DIR} --prefix ${CMAKE_BINARY_DIR}/debian/${APP_NAME}/usr
    COMMENT "Installing project into debian/${APP_NAME} staging directory for packaging..."
    EXCLUDE_FROM_ALL
)