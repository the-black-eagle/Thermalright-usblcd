#!/usr/bin/env python3

import binascii
import time
import usb1
import psutil
import os
from PIL import Image, ImageDraw, ImageFont
import struct
import tempfile


TAG = 1

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

def rgb_to_bgr565(r, g, b):
    """Convert RGB888 to BGR565 format"""
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F  
    b5 = (b >> 3) & 0x1F
    return (b5 << 11) | (g6 << 5) | r5

def image_to_bgr565_chunks(image):
    """Convert PIL image to 3 BGR565 chunks in column-major order"""
    # if image.size != (320, 240):
        # image = image.resize((320, 240))
    
    # # Convert to RGB if needed
    # if image.mode != 'RGB':
        # image = image.convert('RGB')
    
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
                bgr565 = rgb_to_bgr565(r, g, b)
                chunks[chunk_idx].extend(bgr565.to_bytes(2, 'big'))
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

def create_monitoring_image(background_path=None):
    """Create monitoring display image with system info overlay"""

    if background_path and os.path.exists(background_path):
        loaded = Image.open(background_path).convert("RGB")
        if loaded.size != (320, 240):
            loaded = loaded.resize((320, 240), Image.LANCZOS)
        
        # Force it to be identical to generated format
        img = Image.new('RGB', (320, 240))
        img.paste(loaded)
    else:
        img = Image.new('RGB', (320, 240), (20, 245, 20))
        draw = ImageDraw.Draw(img)
        for y in range(240):
            color_val = int(20 + (y / 240) * 40)
            draw.line([(0, y), (320, y)], fill=(color_val, color_val//2, color_val)) 

    draw = ImageDraw.Draw(img)
    
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
    white_text = (0, 0, 0)
    yellow_text = (255, 0, 0)
    cyan_text = (0, 0, 255)
    
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
    
    draw.text((time_x, 20), current_time, fill=white_text, font=font_large)
    draw.text((date_x, 70), date_str, fill=white_text, font=font_small)
    
    # CPU section (left side, larger text)
    draw.text((15, 90), "CPU", fill=yellow_text, font=font_medium)
    
    # CPU temperature (if available)
    if info['cpu_temp']:
        temp_text = f"{info['cpu_temp']:.0f}°C"
        draw.text((15, 115), temp_text, fill=cyan_text, font=font_medium)
    
    # CPU usage percentage
    cpu_text = f"{info['cpu_percent']:.0f}%"
    draw.text((90, 115), cpu_text, fill=cyan_text, font=font_medium)
    
    # CPU frequency (if available)
    try:
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            freq_text = f"{cpu_freq.current:.0f}MHz"
            draw.text((160, 115), freq_text, fill=cyan_text, font=font_medium)
    except:
        pass
    
    # Memory info (compact)
    mem_text = f"RAM: {info['mem_percent']:.0f}% ({info['mem_used_gb']:.1f}GB)"
    draw.text((15, 150), mem_text, fill=white_text, font=font_small)
    
    # Disk info (compact)  
    disk_text = f"Disk: {info['disk_percent']:.0f}% ({info['disk_free_gb']:.0f}GB free)"
    draw.text((15, 170), disk_text, fill=white_text, font=font_small)
    
    # Network info (bottom, compact)
    net_text = f"↑{info['net_sent_mb']:.0f}MB ↓{info['net_recv_mb']:.0f}MB"
    draw.text((15, 200), net_text, fill=white_text, font=font_small)
    
    return img

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
    chunks = image_to_bgr565_chunks(pil_image)
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

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Linux system monitor display")
    parser.add_argument('--background', help='Background image path')
    parser.add_argument('--interval', type=float, default=1.0, help='Update interval in seconds')
    args = parser.parse_args()
    
    vid_want = 0x0402
    pid_want = 0x3922
    
    # Note: You'll need to implement open_dev and send_scsi_command functions
    usbcontext = usb1.USBContext()
    dev = open_dev(vid_want, pid_want, usbcontext)
    dev.setAutoDetachKernelDriver(True)
    dev.claimInterface(0)
    dev.resetDevice()
    
    print("Starting system monitor...")
    
    try:
        while True:
            # Create monitoring image
            img = create_monitoring_image(args.background)
            
            # For testing without USB device
            #img.save(f'monitor_output_{int(time.time())}.png')
            #print(f"Monitor update: {time.strftime('%H:%M:%S')}")
            
            # Upload to display (uncomment when ready)
            upload_pil_image(dev, img)
            
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped")

if __name__ == "__main__":
    main()