#!/usr/bin/env python3

import binascii
import time
import usb1
import psutil
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import struct
import tempfile


TAG = 1

import numpy as np
from PIL import Image

import cv2
from PIL import Image
import time
import threading
import queue

class VideoBackground:
    def __init__(self, video_path, loop=True):
        self.video_path = video_path
        self.loop = loop
        self.cap = None
        self.current_frame = None
        self.fps = 24
        self.frame_duration = 1.0 / self.fps
        self.last_frame_time = 0
        self.frame_queue = queue.Queue(maxsize=24)  # Buffer a few frames
        self.is_playing = False
        self.playback_thread = None

        # Load all frames into memory
        self.frames = []
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Failed to open video: {video_path}")
            return

        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        if actual_fps > 0:
            self.fps = actual_fps
            self.frame_duration = 1.0 / self.fps

        print(f"Video loaded: {video_path}")
        print(f"FPS: {self.fps}")
        print(f"Frame count: {int(cap.get(cv2.CAP_PROP_FRAME_COUNT))}")

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if frame_rgb.shape[:2] != (240, 320):
                frame_rgb = cv2.resize(frame_rgb, (320, 240))

            self.frames.append(Image.fromarray(frame_rgb))

        cap.release()

        if not self.frames:
            print("No frames loaded from video.")
            return

        self.frame_count = len(self.frames)
        self.current_idx = 0
        self.forward = True
        self.current_frame = self.frames[0]

    def _read_next_frame(self):
        """Get next frame in ping-pong order"""
        frame = self.frames[self.current_idx]

        if self.forward:
            self.current_idx += 1
            if self.current_idx >= self.frame_count:
                if self.loop:
                    self.forward = False
                    self.current_idx = self.frame_count - 2  # Step back for reverse
                else:
                    return False
        else:
            self.current_idx -= 1
            if self.current_idx < 0:
                if self.loop:
                    self.forward = True
                    self.current_idx = 1
                else:
                    return False

        self.current_frame = frame
        return True

    def _playback_worker(self):
        """Background thread for smooth video playback"""
        while self.is_playing:
            start_time = time.time()

            if self._read_next_frame() and self.current_frame:
                try:
                    self.frame_queue.put(self.current_frame.copy(), block=False)
                except queue.Full:
                    pass  # Skip frame if buffer is full

            elapsed = time.time() - start_time
            sleep_time = max(0, self.frame_duration - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def start_playback(self):
        """Start video playback in background thread"""
        if not self.frames:
            return False

        self.is_playing = True
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()
        return True

    def stop_playback(self):
        """Stop video playback"""
        self.is_playing = False
        if self.playback_thread:
            self.playback_thread.join(timeout=1.0)

    def get_current_frame(self):
        """Get the most recent video frame"""
        latest_frame = None
        try:
            while True:
                latest_frame = self.frame_queue.get_nowait()
        except queue.Empty:
            pass

        return latest_frame if latest_frame else self.current_frame

    def close(self):
        """Clean up resources"""
        self.stop_playback()
        self.frames = []


def rgb_to_rgb565(r, g, b):
    """Convert RGB to RGB565 format"""
    r565 = r >> 3  # 5 bits
    g565 = g >> 2  # 6 bits
    b565 = b >> 3  # 5 bits
    return (r565 << 11) | (g565 << 5) | b565

def rgb_to_rgb565_quantized_vectorized(rgb_array):
    """Vectorized RGB to BGR565 quantization"""
    # Quantize each channel
    r_q = (rgb_array[:, :, 0] >> 3) << 3  # 5 bits
    g_q = (rgb_array[:, :, 1] >> 2) << 2  # 6 bits  
    b_q = (rgb_array[:, :, 2] >> 3) << 3  # 5 bits
    
    return np.stack([r_q, g_q, b_q], axis=2)

def apply_optimized_bayer_dithering(image):
    """Vectorized Bayer dithering - much faster than Floyd-Steinberg"""
    # 8x8 Bayer matrix for better quality than 4x4
    bayer_8x8 = np.array([
        [ 0, 32,  8, 40,  2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44,  4, 36, 14, 46,  6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [ 3, 35, 11, 43,  1, 33,  9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47,  7, 39, 13, 45,  5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21]
    ]) / 64.0
    
    img_array = np.array(image, dtype=np.float32)
    height, width = img_array.shape[:2]
    
    # Create threshold matrix for entire image
    y_indices, x_indices = np.ogrid[:height, :width]
    threshold_matrix = bayer_8x8[y_indices % 8, x_indices % 8]
    
    # Apply threshold to all channels at once
    # Scale threshold to match quantization step sizes for each channel
    r_threshold = threshold_matrix * (255 / 32)  # 5-bit quantization
    g_threshold = threshold_matrix * (255 / 64)  # 6-bit quantization  
    b_threshold = threshold_matrix * (255 / 32)  # 5-bit quantization
    
    dithered = img_array.copy()
    dithered[:, :, 0] += r_threshold - (255 / 64)  # Center around 0
    dithered[:, :, 1] += g_threshold - (255 / 128)
    dithered[:, :, 2] += b_threshold - (255 / 64)
    
    # Clamp and quantize
    dithered = np.clip(dithered, 0, 255)
    quantized = rgb_to_rgb565_quantized_vectorized(dithered.astype(np.uint8))
    
    return Image.fromarray(quantized)

def apply_blue_noise_dithering(image):
    """Blue noise dithering - good quality with natural-looking noise pattern"""
    # Simple blue noise approximation using random values with spatial filtering
    img_array = np.array(image, dtype=np.float32)
    height, width = img_array.shape[:2]
    
    # Generate spatially filtered noise (approximates blue noise characteristics)
    np.random.seed(42)  # For reproducible results
    noise = np.random.random((height, width)) * 2 - 1  # -1 to 1
    
    # Apply simple spatial filter to reduce low frequencies (crude blue noise)
    from scipy import ndimage
    kernel = np.array([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]]) / 9
    try:
        filtered_noise = ndimage.convolve(noise, kernel, mode='wrap')
    except ImportError:
        # Fallback if scipy not available - use simple high-pass
        filtered_noise = noise - np.roll(np.roll(noise, 1, axis=0), 1, axis=1)
    
    # Scale noise for each channel based on quantization step
    r_noise = filtered_noise * 8   # 5-bit quantization step
    g_noise = filtered_noise * 4   # 6-bit quantization step
    b_noise = filtered_noise * 8   # 5-bit quantization step
    
    dithered = img_array.copy()
    dithered[:, :, 0] += r_noise
    dithered[:, :, 1] += g_noise
    dithered[:, :, 2] += b_noise
    
    # Clamp and quantize
    dithered = np.clip(dithered, 0, 255)
    quantized = rgb_to_rgb565_quantized_vectorized(dithered.astype(np.uint8))
    
    return Image.fromarray(quantized)

def apply_white_noise_dithering(image):
    """Simple white noise dithering - fastest option"""
    img_array = np.array(image, dtype=np.float32)
    height, width = img_array.shape[:2]
    
    # Generate random noise for each channel
    np.random.seed(42)  # For reproducible results
    r_noise = (np.random.random((height, width)) - 0.5) * 16  # ±8 for 5-bit
    g_noise = (np.random.random((height, width)) - 0.5) * 8   # ±4 for 6-bit
    b_noise = (np.random.random((height, width)) - 0.5) * 16  # ±8 for 5-bit
    
    dithered = img_array.copy()
    dithered[:, :, 0] += r_noise
    dithered[:, :, 1] += g_noise
    dithered[:, :, 2] += b_noise
    
    # Clamp and quantize
    dithered = np.clip(dithered, 0, 255)
    quantized = rgb_to_rgb565_quantized_vectorized(dithered.astype(np.uint8))
    
    return Image.fromarray(quantized)

def apply_simple_error_diffusion(image):
    """Simplified error diffusion - faster than Floyd-Steinberg but still sequential"""
    img_array = np.array(image, dtype=np.float32)
    height, width, channels = img_array.shape
    
    dithered = img_array.copy()
    
    for y in range(height - 1):  # Skip last row for simplicity
        for x in range(width - 1):  # Skip last column
            old_pixel = dithered[y, x].astype(int)
            old_pixel = np.clip(old_pixel, 0, 255)
            
            # Quantize
            new_r = (old_pixel[0] >> 3) << 3
            new_g = (old_pixel[1] >> 2) << 2  
            new_b = (old_pixel[2] >> 3) << 3
            new_pixel = np.array([new_r, new_g, new_b])
            
            dithered[y, x] = new_pixel
            error = old_pixel - new_pixel
            
            # Simplified error distribution (only to right and down)
            dithered[y, x + 1] += error * 0.5
            dithered[y + 1, x] += error * 0.5
    
    dithered = np.clip(dithered, 0, 255).astype(np.uint8)
    return Image.fromarray(dithered)

def image_to_rgb565_chunks_fast_dithering(image, dither_method='bayer'):
    """
    Fast dithered conversion with multiple algorithm options
    
    Methods:
    - 'bayer': 8x8 Bayer matrix (best balance of speed/quality)
    - 'blue_noise': Blue noise pattern (good for photos)  
    - 'white_noise': Random noise (fastest)
    - 'simple_error': Simplified error diffusion (slower but good quality)
    """
    
    if dither_method == 'bayer':
        dithered_image = apply_optimized_bayer_dithering(image)
    elif dither_method == 'blue_noise':
        dithered_image = apply_blue_noise_dithering(image)
    elif dither_method == 'white_noise':
        dithered_image = apply_white_noise_dithering(image)
    elif dither_method == 'simple_error':
        dithered_image = apply_simple_error_diffusion(image)
    else:
        raise ValueError(f"Unknown dither method: {dither_method}")
    
    # Get pixel data from dithered image
    pixels = list(dithered_image.getdata())
    
    # Convert to BGR565 and arrange in column-major order
    chunks = [bytearray(), bytearray(), bytearray()]
    chunk_widths = [120, 120, 80]  # pixels per chunk
    chunk_start = 0
    
    for chunk_idx, width in enumerate(chunk_widths):
        for col in range(width):
            actual_col = chunk_start + col
            for row in range(240):
                # Flip Y-axis: read from bottom to top
                flipped_row = 239 - row
                pixel_idx = flipped_row * 320 + actual_col
                r, g, b = pixels[pixel_idx]
                bgr565 = rgb_to_rgb565(r, g, b)
                chunks[chunk_idx].extend(bgr565.to_bytes(2, 'little'))
        chunk_start += width
    
    return [bytes(chunk) for chunk in chunks]

# Original function without dithering for comparison
def image_to_rgb565_chunks(image):
    """Convert PIL image to 3 RGB565 chunks in column-major order (no dithering)"""
    
    pixels = list(image.getdata())
    
    # Convert to BGR565 and arrange in column-major order
    chunks = [bytearray(), bytearray(), bytearray()]
    chunk_widths = [120, 120, 80]  # pixels per chunk
    chunk_start = 0
    
    for chunk_idx, width in enumerate(chunk_widths):
        for col in range(width):
            actual_col = chunk_start + col
            for row in range(240):
                # Flip Y-axis: read from bottom to top
                flipped_row = 239 - row
                pixel_idx = flipped_row * 320 + actual_col
                r, g, b = pixels[pixel_idx]
                rgb565 = rgb_to_rgb565(r, g, b)
                chunks[chunk_idx].extend(rgb565.to_bytes(2, 'little'))
        chunk_start += width
    
    return [bytes(chunk) for chunk in chunks]

def apply_bayer_dithering(image, threshold_map_size=4):
    """Apply Bayer (ordered) dithering - faster but lower quality than Floyd-Steinberg"""
    # 4x4 Bayer matrix
    bayer_4x4 = np.array([
        [ 0,  8,  2, 10],
        [12,  4, 14,  6],
        [ 3, 11,  1,  9],
        [15,  7, 13,  5]
    ]) / 16.0 * 255
    
    img_array = np.array(image, dtype=np.float32)
    height, width, channels = img_array.shape
    
    dithered = np.zeros_like(img_array)
    
    for y in range(height):
        for x in range(width):
            # Get threshold from Bayer matrix
            threshold = bayer_4x4[y % 4, x % 4]
            
            # Add threshold to pixel values
            pixel = img_array[y, x] + threshold - 127.5
            pixel = np.clip(pixel, 0, 255).astype(int)
            
            # Quantize to BGR565
            (new_r, new_g, new_b), _ = rgb_to_rgb565_quantized(
                pixel[0], pixel[1], pixel[2]
            )
            
            dithered[y, x] = [new_r, new_g, new_b]
    
    return Image.fromarray(dithered.astype(np.uint8))

def image_to_rgb565_chunks_with_bayer_dithering(image):
    """Convert PIL image to 3 BGR565 chunks with Bayer dithering (faster alternative)"""
    
    # Apply Bayer dithering
    dithered_image = apply_bayer_dithering(image)
    
    # Get pixel data from dithered image
    pixels = list(dithered_image.getdata())
    
    # Convert to BGR565 and arrange in column-major order
    chunks = [bytearray(), bytearray(), bytearray()]
    chunk_widths = [120, 120, 80]  # pixels per chunk
    chunk_start = 0
    
    for chunk_idx, width in enumerate(chunk_widths):
        for col in range(width):
            actual_col = chunk_start + col
            for row in range(240):
                # Flip Y-axis: read from bottom to top
                flipped_row = 239 - row
                pixel_idx = flipped_row * 320 + actual_col
                r, g, b = pixels[pixel_idx]
                rgb565 = rgb_to_rgb565(r, g, b)
                chunks[chunk_idx].extend(rgb565.to_bytes(2, 'little'))
        chunk_start += width
    
    return [bytes(chunk) for chunk in chunks]

def rgb_to_rgb565_quantized(r, g, b):
    """Convert RGB to BGR565 and return both the quantized values and the BGR565 result"""
    # Quantize to the bit depths used in BGR565
    r_q = (r >> 3) << 3  # 5 bits -> back to 8 bits
    g_q = (g >> 2) << 2  # 6 bits -> back to 8 bits  
    b_q = (b >> 3) << 3  # 5 bits -> back to 8 bits
    
    # Create BGR565 value
    r565 = r >> 3  # 5 bits
    g565 = g >> 2  # 6 bits
    b565 = b >> 3  # 5 bits
    rgb565 = (b565 << 11) | (g565 << 5) | r565
    
    return (r_q, g_q, b_q), rgb565

def apply_floyd_steinberg_dithering(image):
    """Apply Floyd-Steinberg dithering to an image for BGR565 conversion"""
    # Convert to numpy array for easier manipulation
    img_array = np.array(image, dtype=np.float32)
    height, width, channels = img_array.shape
    
    # Create a copy to work with
    dithered = img_array.copy()
    
    for y in range(height):
        for x in range(width):
            # Get the old pixel values
            old_pixel = dithered[y, x].astype(int)
            old_pixel = np.clip(old_pixel, 0, 255)
            
            # Quantize to BGR565 and get the quantized RGB values
            (new_r, new_g, new_b), _ = rgb_to_rgb565_quantized(
                old_pixel[0], old_pixel[1], old_pixel[2]
            )
            new_pixel = np.array([new_r, new_g, new_b])
            
            # Set the new pixel
            dithered[y, x] = new_pixel
            
            # Calculate quantization error
            error = old_pixel - new_pixel
            
            # Distribute error to neighboring pixels using Floyd-Steinberg weights
            if x + 1 < width:
                dithered[y, x + 1] += error * 7/16
            if y + 1 < height:
                if x > 0:
                    dithered[y + 1, x - 1] += error * 3/16
                dithered[y + 1, x] += error * 5/16
                if x + 1 < width:
                    dithered[y + 1, x + 1] += error * 1/16
    
    # Clamp values and convert back to uint8
    dithered = np.clip(dithered, 0, 255).astype(np.uint8)
    return Image.fromarray(dithered)

def image_to_rgb565_chunks_with_dithering(image):
    """Convert PIL image to 3 BGR565 chunks in column-major order with dithering"""
    
    # Apply Floyd-Steinberg dithering first
    dithered_image = apply_floyd_steinberg_dithering(image)
    
    # Get pixel data from dithered image
    pixels = list(dithered_image.getdata())
    
    # Convert to BGR565 and arrange in column-major order
    chunks = [bytearray(), bytearray(), bytearray()]
    chunk_widths = [120, 120, 80]  # pixels per chunk
    chunk_start = 0
    
    for chunk_idx, width in enumerate(chunk_widths):
        for col in range(width):
            actual_col = chunk_start + col
            for row in range(240):
                # Flip Y-axis: read from bottom to top
                flipped_row = 239 - row
                pixel_idx = flipped_row * 320 + actual_col
                r, g, b = pixels[pixel_idx]
                rgb565 = rgb_to_rgb565(r, g, b)
                chunks[chunk_idx].extend(rgb565.to_bytes(2, 'little'))
        chunk_start += width
    
    return [bytes(chunk) for chunk in chunks]

def send_scsi_command(dev, cdb, data_out=None, data_in_len=0):
    """
    Send a SCSI command over USB Bulk-Only Transport (BOT).
    """
    global TAG
    direction = 0x80 if data_in_len else 0x00
    data_len = data_in_len if data_in_len else (len(data_out) if data_out else 0)
    cdb_len = len(cdb)

    # Build CBW (31 bytes)
    cbw = bytearray(31)
    cbw[0:4]  = b'USBC'
    cbw[4:8]  = TAG.to_bytes(4, 'little')
    cbw[8:12] = data_len.to_bytes(4, 'little')
    cbw[12]   = direction
    cbw[13]   = 0  # LUN
    cbw[14]   = cdb_len
    cbw[15:15+cdb_len] = cdb

    # Send CBW
    dev.bulkWrite(0x02, cbw)

    # Data phase
    data_in = None
    if data_in_len:
        data_in = dev.bulkRead(0x81, data_in_len)
    elif data_out:
        dev.bulkWrite(0x02, data_out)

    # CSW (always 13 bytes)
    csw = dev.bulkRead(0x81, 13)

    TAG += 1
    return data_in, csw

def rgb_to_display_format(r, g, b):
    """Convert RGB to the 565 format the display expects"""
    r565 = r >> 3
    g565 = g >> 2  
    b565 = b >> 3
    return (r565 << 11) | (g565 << 5) | b565  # RGB565 bit order

def image_to_rgb565_chunks_original(image):
    """Convert PIL image to 3 BGR565 chunks in column-major order"""

    
    pixels = list(image.getdata())
    
    # Convert to BGR565 and arrange in column-major order
    chunks = [bytearray(), bytearray(), bytearray()]
    chunk_widths = [120, 120, 80]  # pixels per chunk
    chunk_start = 0
    
    for chunk_idx, width in enumerate(chunk_widths):
        for col in range(width):
            actual_col = chunk_start + col
            for row in range(240):
                # Flip Y-axis: read from bottom to top
                flipped_row = 239 - row
                pixel_idx = flipped_row * 320 + actual_col
                r, g, b = pixels[pixel_idx]
                rgb565 = rgb_to_display_format(r, g, b)
                chunks[chunk_idx].extend(rgb565.to_bytes(2, 'little'))
        chunk_start += width
    
    return [bytes(chunk) for chunk in chunks]

def get_system_info():
    """Collect system monitoring data"""
    info = {}
    
    # CPU info
    info['cpu_percent'] = psutil.cpu_percent(interval=0.1)
    info['cpu_count'] = psutil.cpu_count()
    
    # Memory info  
    mem = psutil.virtual_memory()
    info['mem_percent'] = mem.percent
    info['mem_used_gb'] = mem.used / (1024**3)
    info['mem_total_gb'] = mem.total / (1024**3)
    
    # Temperature (if available)
    try:
        temps = psutil.sensors_temperatures()
        #print(f"temps {temps}")
        if 'k10temp' in temps:
            info['cpu_temp'] = max([sensor.current for sensor in temps['k10temp']])
        elif 'cpu_thermal' in temps:  # Raspberry Pi
            info['cpu_temp'] = temps['cpu_thermal'][0].current
        else:
            info['cpu_temp'] = None
    except:
        info['cpu_temp'] = None
    
    # Disk usage
    disk = psutil.disk_usage('/')
    info['disk_percent'] = (disk.used / disk.total) * 100
    info['disk_free_gb'] = disk.free / (1024**3)
    
    # Network (basic)
    net = psutil.net_io_counters()
    info['net_sent_mb'] = net.bytes_sent / (1024**2)
    info['net_recv_mb'] = net.bytes_recv / (1024**2)
    
    # Load average
    info['load_avg'] = os.getloadavg()[0] if hasattr(os, 'getloadavg') else None
    
    return info

def create_background_img(background_path=None, video_background=None):
    """Create background image - supports both static images and video frames"""
    if video_background:
        # Get current video frame
        frame = video_background.get_current_frame()
        if frame:
            return frame
        # Fallback to static background if video fails
    
    if background_path and os.path.exists(background_path):
        loaded = Image.open(background_path).convert("RGB")
        if loaded.size != (320, 240):
            loaded = loaded.resize((320, 240), Image.LANCZOS)
        
        # Force it to be identical to generated format
        img = Image.new('RGB', (320, 240))
        img.paste(loaded)
    else:
        # Default generated background
        img = Image.new('RGB', (320, 240), (20, 40, 20))
        draw = ImageDraw.Draw(img)
        for y in range(240):
            color_val = int(20 + (y / 240) * 40)
            draw.line([(0, y), (320, y)], fill=(color_val, color_val//2, color_val)) 
    return img

def create_monitoring_image(bgimg):
    """Create monitoring display image with system info overlay"""

    draw = ImageDraw.Draw(bgimg)
    
    # Load larger fonts for better readability on 2.5" screen
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", 48)
        font_medium = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", 24)
        font_small = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSansMono.ttf", 18)
    except:
        try:
            font_large = font_medium = font_small = ImageFont.load_default()
        except:
            font_large = font_medium = font_small = None
    
    # Get system info
    info = get_system_info()
    
    # Colors for better visibility
    text1 = (0, 0, 0)
    text2 = (0, 255, 0)
    text3 = (0, 0, 255)
    
    # Time at top center (large)
    current_time = time.strftime("%H:%M")
    date_str = time.strftime("%d/%m  %a").upper()
    
    # Calculate text width for centering
    time_bbox = draw.textbbox((0, 0), current_time, font=font_large)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = (320 - time_width) // 2
    
    date_bbox = draw.textbbox((0, 0), date_str, font=font_small)
    date_width = date_bbox[2] - date_bbox[0]
    date_x = (320 - date_width) // 2
    
    draw.text((time_x, 20), current_time, fill=text1, font=font_large)
    draw.text((date_x, 70), date_str, fill=text1, font=font_small)
    
    # CPU section (left side, larger text)
    draw.text((15, 90), "CPU", fill=text3, font=font_medium)
    
    # CPU temperature (if available)
    if info['cpu_temp']:
        temp_text = f"{info['cpu_temp']:.0f}°C"
        draw.text((15, 115), temp_text, fill=text2, font=font_medium)
    
    # CPU usage percentage
    cpu_text = f"{info['cpu_percent']:.0f}%"
    draw.text((90, 115), cpu_text, fill=text2, font=font_medium)
    
    # CPU frequency (if available)
    try:
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            freq_text = f"{cpu_freq.current:.0f}MHz"
            draw.text((160, 115), freq_text, fill=text2, font=font_medium)
    except:
        pass
    
    # Memory info (compact)
    mem_text = f"RAM: {info['mem_percent']:.0f}% ({info['mem_used_gb']:.1f}GB)"
    draw.text((15, 150), mem_text, fill=text1, font=font_small)
    
    # Disk info (compact)  
    disk_text = f"Disk: {info['disk_percent']:.0f}% ({info['disk_free_gb']:.0f}GB free)"
    draw.text((15, 170), disk_text, fill=text1, font=font_small)
    
    # Network info (bottom, compact)
    net_text = f"↑{info['net_sent_mb']:.0f}MB ↓{info['net_recv_mb']:.0f}MB"
    draw.text((15, 200), net_text, fill=text1, font=font_small)
    
    return bgimg

def upload_image(dev, chunk_files):
    """Upload image chunks to display"""
    for filename, index, size in chunk_files:
        with open(filename, "rb") as f:
            data = f.read()
        if len(data) != size:
            raise ValueError(f"{filename} size mismatch: expected {size}, got {len(data)}")
        
        # Build vendor-specific CDB (16 bytes)
        cdb = bytearray(16)
        cdb[0] = 0xF5     # vendor command
        cdb[1] = 0x01
        cdb[2] = 0x01
        cdb[3] = index    # chunk index (0,1,2)
        # last 4 bytes = length (little-endian)
        cdb[12:16] = size.to_bytes(4, 'little')
        
        #print(f"Sending chunk {index} ({size} bytes)")
        # Note: send_scsi_command function needs to be implemented
        csw = send_scsi_command(dev, cdb, data_out=data)

def upload_pil_image(dev, pil_image):
    """Convert PIL image to chunks and upload directly to display"""
    chunks = image_to_rgb565_chunks(pil_image)
    #chunks = image_to_rgb565_chunks_fast_dithering(pil_image, 'bayer')
    chunk_sizes = [57600, 57600, 38400]
    
    for index, (chunk_data, expected_size) in enumerate(zip(chunks, chunk_sizes)):
        if len(chunk_data) != expected_size:
            raise ValueError(f"Chunk {index} size mismatch: expected {expected_size}, got {len(chunk_data)}")
        
        # Build vendor-specific CDB (16 bytes)
        cdb = bytearray(16)
        cdb[0] = 0xF5     # vendor command
        cdb[1] = 0x01
        cdb[2] = 0x01
        cdb[3] = index    # chunk index (0,1,2)
        cdb[12:16] = expected_size.to_bytes(4, 'little')
        
        #print(f"Sending chunk {index} ({expected_size} bytes)")
        csw = send_scsi_command(dev, cdb, data_out=chunk_data)

def open_dev(vid_want, pid_want, usbcontext=None):
    if usbcontext is None:
        usbcontext = usb1.USBContext()
    
    print("Scanning for devices...")
    for udev in usbcontext.getDeviceList(skip_on_error=True):
        vid = udev.getVendorID()
        pid = udev.getProductID()
        if (vid, pid) == (vid_want, pid_want):
            print("Found device")
            print("Bus %03i Device %03i: ID %04x:%04x" % (
                udev.getBusNumber(),
                udev.getDeviceAddress(),
                vid,
                pid))
            return udev.open()
    raise Exception("Failed to find a device")

def run_monitoring_with_video(args, dev):
    print("Starting system monitor with video support...")
    
    # Initialize video background if specified
    video_bg = None
    if hasattr(args, 'video') and args.video:
        video_bg = VideoBackground(args.video, loop=True)
        if video_bg.frames:
            video_bg.start_playback()
            print(f"Video playback started: {args.video}")
        else:
            print("Failed to load video, falling back to static background")
            video_bg = None
    
    try:
        while True:
            # Get current background (video frame or static)
            bgimg = create_background_img(
                background_path=getattr(args, 'background', None),
                video_background=video_bg
            )
            
            # Create monitoring image with current background
            img = create_monitoring_image(bgimg)
            
            # Upload to display
            upload_pil_image(dev, img)
            
            # Update rate - for 24fps video, update every ~42ms
            # But system monitor probably doesn't need to be that fast
            time.sleep(0.1)  # 10 FPS update rate
            
    except KeyboardInterrupt:
        print("Stopping monitor...")
    finally:
        if video_bg:
            video_bg.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Linux system monitor display")
    parser.add_argument('--background', help='Background image path')
    parser.add_argument('--interval', type=float, default=0.5, help='Update interval in seconds')
    parser.add_argument('--video', type=str, help='MP4 video file for animated background')

    args = parser.parse_args()
    
    vid_want = 0x0402
    pid_want = 0x3922
    
    # Note: You'll need to implement open_dev and send_scsi_command functions
    usbcontext = usb1.USBContext()
    dev = open_dev(vid_want, pid_want, usbcontext)
    dev.setAutoDetachKernelDriver(True)
    dev.claimInterface(0)
    dev.resetDevice()
    
    run_monitoring_with_video(args, dev)


if __name__ == "__main__":
    main()