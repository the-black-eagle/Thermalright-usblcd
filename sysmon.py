#!/usr/bin/env python3

import os
import time
import threading
import usb1
from datetime import datetime
import psutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

TAG = 1
_sysinfo_poller = None

# -------------------------------
# System Info Poller
# -------------------------------
class SystemInfoPoller:
    """Background system info poller."""

    def __init__(self, fast_interval=0.5, slow_interval=5.0):
        self.fast_interval = fast_interval
        self.slow_interval = slow_interval
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._info = {
            "cpu_percent": 0,
            "cpu_count": 0,
            "cpu_freq": 0,
            "cpu_temp": 0,
            "mem_percent": 0,
            "mem_used_gb": 0,
            "disk_percent": 0,
            "disk_free_gb": 0,
            "net_sent_mb": 0,
            "net_recv_mb": 0
        }

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread: self._thread.join(timeout=1.0)

    def get_info(self):
        with self._lock:
            return dict(self._info)

    def _poll_loop(self):
        next_fast = next_slow = 0
        while self._running:
            now = time.time()
            updated = {}
            if now >= next_fast:
                updated.update(self._poll_fast())
                next_fast = now + self.fast_interval
            if now >= next_slow:
                updated.update(self._poll_slow())
                next_slow = now + self.slow_interval
            if updated:
                with self._lock:
                    self._info.update(updated)
            time.sleep(0.05)

    def _poll_fast(self):
        info = {}
        try:
            info['cpu_percent'] = psutil.cpu_percent(interval=None)
        except: info['cpu_percent'] = 0
        try:
            temps = psutil.sensors_temperatures()
            cpu_temp = None

            for key in ('k10temp', 'coretemp'):
                if key in temps:
                    cpu_temp = max(sensor.current for sensor in temps[key])
                    break

            info['cpu_temp'] = cpu_temp if cpu_temp is not None else 0

        except: info['cpu_temp'] = 0
        try:
            mem = psutil.virtual_memory()
            info['mem_percent'] = mem.percent
            info['mem_used_gb'] = mem.used / (1024**3)
        except: info['mem_percent'] = info['mem_used_gb'] = 0
        return info

    def _poll_slow(self):
        info = {}
        try: info['cpu_count'] = psutil.cpu_count(logical=True) or 0
        except: info['cpu_count'] = 0
        try:
            freq = psutil.cpu_freq()
            info['cpu_freq'] = freq.current if freq else 0
        except: info['cpu_freq'] = 0
 # --- Disk info across all real drives ---
        try:
            total = used = free = 0
            for part in psutil.disk_partitions(all=False):
                # Skip virtual/loopback/temporary filesystems
                if part.fstype.lower() in (
                    '', 'tmpfs', 'devtmpfs', 'proc', 'sysfs',
                    'cgroup', 'overlay', 'squashfs', 'ramfs'
                ):
                    continue
                if part.device.startswith('/dev/loop') or part.device.startswith('/dev/sr'):
                    continue
                if "run" in part.mountpoint:
                    continue
    
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except PermissionError:
                    continue
    
                total += usage.total
                used  += usage.used
                free  += usage.free
    
            if total > 0:
                info['disk_percent'] = used / total * 100
                info['disk_free_gb'] = free / 1e9
            else:
                info['disk_percent'] = 0
                info['disk_free_gb'] = 0
        except Exception:
            info['disk_percent'] = 0
            info['disk_free_gb'] = 0
        try:
            net = psutil.net_io_counters()
            info['net_sent_mb'] = net.bytes_sent / 1e6
            info['net_recv_mb'] = net.bytes_recv / 1e6
        except: info['net_sent_mb'] = info['net_recv_mb'] = 0
        return info

# -------------------------------
# Video Background
# -------------------------------
class VideoBackground:
    def __init__(self, path, mode="loop", target_fps=20):
        self.path = path
        self.mode = mode
        self.frames_pil = []
        self._frame_index = 0
        self._forward = True
        self._lock = threading.Lock()
        self._playing = False
        self._thread = None
        self._fps = target_fps
        self._preload_frames(target_fps)

    def _preload_frames(self, target_fps):
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened(): return
        original_fps = cap.get(cv2.CAP_PROP_FPS) or 24
        frame_interval = original_fps / target_fps
        frames = []
        frame_count = 0
        next_frame_to_keep = 0
        while True:
            ret, frame = cap.read()
            if not ret: break
            if frame_count >= next_frame_to_keep:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if frame.shape[:2] != (240, 320):
                    frame = cv2.resize(frame, (320, 240))
                pil_frame = Image.fromarray(frame)
                frames.append(pil_frame)
                next_frame_to_keep += frame_interval
            frame_count += 1
        cap.release()
        self.frames_pil = frames

    def start_playback(self):
        if self._playing or not self.frames_pil: return
        self._playing = True
        self._thread = threading.Thread(target=self._play_loop, daemon=True)
        self._thread.start()

    def stop_playback(self):
        self._playing = False
        if self._thread: self._thread.join(timeout=1.0)

    def _play_loop(self):
        """Play preloaded frames at the target FPS, correcting for jitter."""
        next_frame_time = time.perf_counter()
        frame_interval = 1.0 / self._fps
    
        while self._playing and self.frames_pil:
            now = time.perf_counter()
            if now >= next_frame_time:
                # Advance frame first
                with self._lock:
                    if self.mode == "loop":
                        self._frame_index = (self._frame_index + 1) % len(self.frames_pil)
                    elif self.mode == "pingpong":
                        if self._forward:
                            self._frame_index += 1
                            if self._frame_index >= len(self.frames_pil) - 1:
                                self._forward = False
                        else:
                            self._frame_index -= 1
                            if self._frame_index <= 0:
                                self._forward = True
    
                # Schedule next frame
                next_frame_time += frame_interval
    
            # Sleep a tiny bit to avoid busy-wait
            time.sleep(0.001)

    def get_current_frame(self):
        if not self.frames_pil: return None
        with self._lock:
            return self.frames_pil[self._frame_index].copy()

# -------------------------------
# Video LCD Sender
# -------------------------------
class VideoLCDSender:
    def __init__(self, dev):
        self.dev = dev
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._latest_chunks = None
        self._new_frame_event = threading.Event()

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread: self._thread.join(timeout=1.0)

    def set_latest_chunks(self, chunks):
        with self._lock:
            self._latest_chunks = chunks
        self._new_frame_event.set()

    def _send_loop(self):
        while self._running:
            if self._new_frame_event.wait(timeout=0.1):
                self._new_frame_event.clear()
                with self._lock:
                    chunks = list(self._latest_chunks) if self._latest_chunks else None
                if chunks:
                    for idx, chunk in enumerate(chunks):
                        cdb = bytearray(16)
                        cdb[0] = 0xF5
                        cdb[1] = 0x01
                        cdb[2] = 0x01
                        cdb[3] = idx
                        cdb[12:16] = len(chunk).to_bytes(4,'little')
                        try: send_scsi_command(self.dev, cdb, data_out=chunk)
                        except Exception as e: print(f"Failed to send chunk {idx}: {e}")

# -------------------------------
# Image/Dithering Utilities
# -------------------------------

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

def rgb_to_rgb565(r,g,b):
    r565 = r>>3
    g565 = g>>2
    b565 = b>>3
    return (r565<<11)|(g565<<5)|b565

def image_to_rgb565_chunks(image):
    """Column-major conversion (no dithering)"""
    pixels = list(image.getdata())
    chunks = [bytearray(), bytearray(), bytearray()]
    chunk_widths = [120,120,80]
    start=0
    for i,w in enumerate(chunk_widths):
        for col in range(w):
            ac = start+col
            for row in range(240):
                flipped = 239-row
                r,g,b=pixels[flipped*320+ac]
                chunks[i].extend(rgb_to_rgb565(r,g,b).to_bytes(2,'little'))
        start+=w
    return [bytes(c) for c in chunks]

# -------------------------------
# USB/Display Utilities
# -------------------------------
def send_scsi_command(dev, cdb, data_out=None, data_in_len=0):
    global TAG
    direction = 0x80 if data_in_len else 0x00
    data_len = data_in_len if data_in_len else (len(data_out) if data_out else 0)
    cbw = bytearray(31)
    cbw[0:4]=b'USBC'
    cbw[4:8]=TAG.to_bytes(4,'little')
    cbw[8:12]=data_len.to_bytes(4,'little')
    cbw[12]=direction
    cbw[14]=len(cdb)
    cbw[15:15+len(cdb)]=cdb
    dev.bulkWrite(0x02, cbw)
    if data_in_len: data_in = dev.bulkRead(0x81, data_in_len)
    elif data_out: dev.bulkWrite(0x02, data_out)
    dev.bulkRead(0x81, 13)
    TAG+=1

def open_dev(vid_want, pid_want, usbcontext=None):
    if usbcontext is None: usbcontext=usb1.USBContext()
    for udev in usbcontext.getDeviceList(skip_on_error=True):
        if (udev.getVendorID(), udev.getProductID())==(vid_want,pid_want):
            return udev.open()
    raise Exception("Device not found")

# -------------------------------
# Monitoring / Overlay
# -------------------------------
def get_system_info():
    global _sysinfo_poller
    if _sysinfo_poller is None:
        _sysinfo_poller=SystemInfoPoller()
        _sysinfo_poller.start()
    return _sysinfo_poller.get_info()

def create_background_img(background_path=None, video_background=None):
    if video_background:
        frame=video_background.get_current_frame()
        if frame: return frame
    if background_path and os.path.exists(background_path):
        img=Image.open(background_path).convert("RGB").resize((320,240))
        return img
    img=Image.new('RGB',(320,240),(20,40,20))
    draw=ImageDraw.Draw(img)
    for y in range(240):
        val=int(20+(y/240)*40)
        draw.line([(0,y),(320,y)],fill=(val,val//2,val))
    img = apply_optimized_bayer_dithering(img)
    return img

def create_monitoring_image(bgimg, font_large, font_medium, font_small):
    draw=ImageDraw.Draw(bgimg)
    info=get_system_info()
    text1,text2,text3=(255,255,255),(0,255,0),(0,0,255)
    current_time=time.strftime("%H:%M")
    date_str=time.strftime("%d/%m  %a").upper()
    time_bbox = draw.textbbox((0, 0), current_time, font=font_large)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = (320 - time_width) // 2
    
    date_bbox = draw.textbbox((0, 0), date_str, font=font_small)
    date_width = date_bbox[2] - date_bbox[0]
    date_x = (320 - date_width) // 2
    
    draw.text((time_x, 20), current_time, fill=text1, font=font_large)
    draw.text((date_x, 70), date_str, fill=text1, font=font_small)
    draw.text((15,90),"CPU",text3,font_medium)
    if info.get('cpu_temp') is not None: draw.text((15,115),f"{info['cpu_temp']:.0f}°C",text2,font_medium)
    if info.get('cpu_percent') is not None: draw.text((90,115),f"{info['cpu_percent']:.0f}%",text2,font_medium)
    if info.get('cpu_freq') is not None: draw.text((160,115),f"{info['cpu_freq']:.0f}MHz",text2,font_medium)
    if info.get('mem_percent') is not None and info.get('mem_used_gb') is not None:
        draw.text((15,150),f"RAM: {info['mem_percent']:.0f}% ({info['mem_used_gb']:.1f}GB)",text1,font_small)
    if info.get('disk_percent') is not None:
        draw.text((15,170),f"Disk: {info['disk_percent']:.0f}% ({info['disk_free_gb']:.0f}GB free)",text1,font_small)
    if info.get('net_sent_mb') is not None:
        draw.text((15,200),f"↑{info['net_sent_mb']:.0f}MB ↓{info['net_recv_mb']:.0f}MB",text1,font_small)
    return bgimg

# -------------------------------
# Main Loop
# -------------------------------
def run_monitoring_with_video(args, dev):
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",48)
        font_medium = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",24)
        font_small = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSansMono.ttf",18)
    except: font_large=font_medium=font_small=ImageFont.load_default()
    global _sysinfo_poller
    _sysinfo_poller = SystemInfoPoller(fast_interval=args.info_interval)
    _sysinfo_poller.start()
    video_bg = VideoBackground(args.video,args.video_mode) if getattr(args,'video',None) else None
    video_sender = VideoLCDSender(dev) if video_bg else None
    if video_bg: video_bg.start_playback()
    if video_sender: video_sender.start()
    try:
        while True:
            start = time.perf_counter()
            bgimg=create_background_img(getattr(args,'background',None),video_bg)
            img=create_monitoring_image(bgimg,font_large,font_medium,font_small)
            chunks=image_to_rgb565_chunks(img)
            if video_sender: video_sender.set_latest_chunks(chunks)
            else:
                for idx,chunk in enumerate(chunks):
                    cdb=bytearray(16)
                    cdb[0]=0xF5;cdb[1]=0x01;cdb[2]=0x01;cdb[3]=idx;cdb[12:16]=len(chunk).to_bytes(4,'little')
                    send_scsi_command(dev,cdb,data_out=chunk)
            if not video_sender: time.sleep(args.interval)
            end_time = time.perf_counter()
            #print(f"  loop time: {(end_time-start)*1000:.1f}ms")
            time.sleep(0.001)
    except KeyboardInterrupt: print("Stopping monitor...")
    finally:
        if video_sender: video_sender.stop()
        if video_bg: video_bg.stop_playback()
        if _sysinfo_poller: _sysinfo_poller.stop()

# -------------------------------
# Entry Point
# -------------------------------
def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--background', type=str, help='path to a 320x240 png', metavar='/home/lcdtest/background/01.png')
    parser.add_argument('--interval',type=float,default=0.5, help='Time to wait between frames if not playing video', metavar='0.5')
    parser.add_argument('--video',type=str, help='path/to/a/320x240/video.mp4', metavar='/home/lcdtest/video/01.mp4')
    parser.add_argument('--info-interval',type=float,default=0.5, help='delay between updating info metrics (cpu info mainly) in seconds', metavar='0.5')
    parser.add_argument('--video-mode',choices=['loop','pingpong'],default='loop', help='Loop at the end of the video or play backwards to the beginning')
    args=parser.parse_args()
    vid_want,pid_want=0x0402,0x3922
    usbcontext=usb1.USBContext()
    dev=open_dev(vid_want,pid_want,usbcontext)
    dev.setAutoDetachKernelDriver(True)
    dev.claimInterface(0)
    dev.resetDevice()
    run_monitoring_with_video(args,dev)

if __name__=="__main__":
    main()
