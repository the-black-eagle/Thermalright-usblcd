# Copyright 2005 Gary Moore (g.moore(AT)gmx.co.uk)

   # Licensed under the Apache License, Version 2.0 (the "License");
   # you may not use this file except in compliance with the License.
   # You may obtain a copy of the License at

       # http://www.apache.org/licenses/LICENSE-2.0

   # Unless required by applicable law or agreed to in writing, software
   # distributed under the License is distributed on an "AS IS" BASIS,
   # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   # See the License for the specific language governing permissions and
   # limitations under the License.



import os
import io
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, font, simpledialog, messagebox, Button
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont
import subprocess
import time
import json
import cProfile
import pstats
import queue
import threading
import lcd_driver
from collections import deque

READY_TIMEOUT = 30  # seconds

def wait_for_lcd_ready(lcd_driver):
    start = time.time()
    while time.time() - start < READY_TIMEOUT:
        if lcd_driver.device_ready():
            return True
        time.sleep(0.2)
    return True

def on_reset_click():
    try:
        lcd_driver.reset_transport()
        print("Transport reset triggered")
    except Exception as e:
        print(f"Reset failed: {e}")


class DraggableTextPillow:
    """A Pillow-based draggable text item."""
    _font_cache = {}

    def __init__(self, tag, text, x, y, font_config, color, update_callback):
        self.tag = tag
        self.text = text
        self.x = x
        self.y = y
        self.font_config = font_config
        self.color = color
        self.style = {
            "style": font_config.get("style", "normal"),
            "weight": "bold" if "bold" in font_config.get("style", "") else "normal",
            "slant": "italic" if "italic" in font_config.get("style", "") else "roman",
        }
        self.update_callback = update_callback
        self.dragging = False
        self._pil_font = None
        self._last_font_config = None

    def find_font_path(self, family: str, style: str = "normal") -> str | None:
        """
        Use fc-list to find a matching font file for given family+style.
        Returns path to .ttf/.otf file or None if not found.
        """
        try:
            # Primary method: Use fc-list with family filter (this works on your system)
            result = subprocess.run(
                ["fc-list", f":family={family}"],
                capture_output=True, text=True, check=True
            )
            
            candidates = []
            for line in result.stdout.splitlines():
                if ":" in line:
                    path = line.split(":")[0].strip()
                    if os.path.exists(path):
                        # Extract style info from the line if available
                        style_info = ""
                        if ":style=" in line:
                            try:
                                style_info = line.split(":style=")[1].lower()
                            except IndexError:
                                style_info = ""
                        candidates.append((path, style_info))
    
            if not candidates:
                print(f"No font found for family: {family}")
                return None
    
            # Filter by style if specified
            style = style.lower()
            if style != "normal" and len(candidates) > 1:
                style_filtered = []
                
                for path, font_style in candidates:
                    path_lower = path.lower()
                    font_style_lower = font_style.lower()
                    
                    # Check for bold
                    if "bold" in style:
                        if ("bold" in font_style_lower or "bold" in path_lower) and \
                           not ("italic" in style or "oblique" in style or 
                                "italic" in font_style_lower or "oblique" in font_style_lower):
                            style_filtered.append((path, font_style))
                    
                    # Check for italic/oblique
                    elif "italic" in style or "oblique" in style:
                        if ("italic" in font_style_lower or "oblique" in font_style_lower or 
                            "italic" in path_lower or "oblique" in path_lower) and \
                           not ("bold" in style or "bold" in font_style_lower or "bold" in path_lower):
                            style_filtered.append((path, font_style))
                    
                    # Check for bold italic
                    elif "bold" in style and ("italic" in style or "oblique" in style):
                        if ("bold" in font_style_lower or "bold" in path_lower) and \
                           ("italic" in font_style_lower or "oblique" in font_style_lower or 
                            "italic" in path_lower or "oblique" in path_lower):
                            style_filtered.append((path, font_style))
                
                if style_filtered:
                    candidates = style_filtered
            
            # For normal style, prefer fonts without Bold/Italic in the name
            elif style == "normal" and len(candidates) > 1:
                normal_candidates = []
                for path, font_style in candidates:
                    path_lower = path.lower()
                    font_style_lower = font_style.lower()
                    
                    if not any(keyword in path_lower or keyword in font_style_lower 
                             for keyword in ["bold", "italic", "oblique", "condensed", "light", "thin"]):
                        normal_candidates.append((path, font_style))
                
                if normal_candidates:
                    candidates = normal_candidates
            
            # Final preference: avoid condensed fonts if regular variants exist
            if len(candidates) > 1:
                non_condensed = []
                for path, font_style in candidates:
                    path_lower = path.lower()
                    font_style_lower = font_style.lower()
                    
                    if "condensed" not in path_lower and "condensed" not in font_style_lower:
                        non_condensed.append((path, font_style))
                
                if non_condensed:
                    candidates = non_condensed
    
            # Return the first valid candidate
            for path, _ in candidates:
                if os.path.exists(path):
                    return path
                    
            print(f"Font files not found on filesystem for: {family}")
            return None
            
        except subprocess.CalledProcessError as e:
            print(f"fc-list command failed: {e}")
            return None
        except Exception as e:
            print(f"Font lookup failed for {family}: {e}")
            return None

    def get_fallback_fonts(self):
        """Return a list of common fallback font paths to try"""
        common_fonts = [
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", 
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/System/Library/Fonts/Arial.ttf",  # macOS
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
            "C:/Windows/Fonts/arial.ttf",  # Windows
            "C:/Windows/Fonts/Arial.ttf",  # Windows
        ]
        
        # Return only fonts that actually exist
        return [font for font in common_fonts if os.path.exists(font)]

    @classmethod
    def get_font(cls, font_config):
        """Static method for getting fonts (legacy compatibility)"""
        key = (font_config['family'], font_config['size'], font_config.get('style', 'normal'))
        if key not in cls._font_cache:
            try:
                # If family looks like a path, use it directly
                family = font_config['family']
                if os.path.exists(family) and (family.endswith('.ttf') or family.endswith('.otf')):
                    cls._font_cache[key] = ImageFont.truetype(family, font_config['size'])
                else:
                    # Try to find the font
                    instance = cls("temp", "", 0, 0, font_config, "#000000", None)
                    font_path = instance.find_font_path(family, font_config.get('style', 'normal'))
                    
                    if font_path and os.path.exists(font_path):
                        cls._font_cache[key] = ImageFont.truetype(font_path, font_config['size'])
                    else:
                        # Try fallback fonts
                        fallback_fonts = instance.get_fallback_fonts()
                        font_loaded = False
                        for fallback in fallback_fonts:
                            try:
                                cls._font_cache[key] = ImageFont.truetype(fallback, font_config['size'])
                                font_loaded = True
                                print(f"Using fallback font: {fallback}")
                                break
                            except Exception:
                                continue
                        
                        if not font_loaded:
                            cls._font_cache[key] = ImageFont.load_default()
                            print("Using default font - no TrueType fonts found")
                            
            except Exception as e:
                print(f"Font loading error: {e}")
                cls._font_cache[key] = ImageFont.load_default()
                
        return cls._font_cache[key]

    def _get_font(self):
        """Return cached PIL font, reload if config changed."""
        if self._pil_font is None or (self._last_font_config and self.font_config != self._last_font_config):
            self._last_font_config = self.font_config.copy()
            size = self.font_config.get("size", 24)
            family = self.font_config.get("family", "DejaVu Sans")
            style = self.font_config.get("style", "normal")
            
            font_path = None
            
            # If family is already a path, use it directly
            if os.path.exists(family) and (family.endswith('.ttf') or family.endswith('.otf')):
                font_path = family
            else:
                # Try to find the font
                font_path = self.find_font_path(family, style)
            
            # Try to load the font
            try:
                if font_path and os.path.exists(font_path):
                    self._pil_font = ImageFont.truetype(font_path, size)
                else:
                    # Try fallback fonts
                    fallback_fonts = self.get_fallback_fonts()
                    font_loaded = False
                    
                    for fallback in fallback_fonts:
                        try:
                            self._pil_font = ImageFont.truetype(fallback, size)
                            print(f"Using fallback font: {fallback}")
                            font_loaded = True
                            break
                        except Exception as e:
                            print(f"Failed to load fallback {fallback}: {e}")
                            continue
                    
                    if not font_loaded:
                        self._pil_font = ImageFont.load_default()
                        print("Using PIL default font")
                        
            except Exception as e:
                print(f"Font loading error: {e}")
                self._pil_font = ImageFont.load_default()
                
        return self._pil_font

    def draw(self, image_draw: ImageDraw.Draw):
        pil_font = self._get_font()
        image_draw.text((self.x, self.y), self.text, font=pil_font, fill=self.color)

    def contains(self, px, py):
        pil_font = self._get_font()  # Use instance method instead of class method
        try:
            # getbbox returns (x0, y0, x1, y1)
            bbox = pil_font.getbbox(self.text)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            return self.x <= px <= self.x + width and self.y <= py <= self.y + height
        except Exception:
            # Fallback for older PIL versions or default fonts
            try:
                width, height = pil_font.getsize(self.text)
                return self.x <= px <= self.x + width and self.y <= py <= self.y + height
            except Exception:
                # Ultimate fallback - assume reasonable text size
                estimated_width = len(self.text) * (self.font_config.get("size", 24) * 0.6)
                estimated_height = self.font_config.get("size", 24)
                return self.x <= px <= self.x + estimated_width and self.y <= py <= self.y + estimated_height

    def move(self, dx, dy, max_width=320, max_height=240, margin=5, update_lcd=True):
        self.x = max(margin, min(self.x + dx, max_width - margin))
        self.y = max(margin, min(self.y + dy, max_height - margin))
    
        # Only update LCD if explicitly requested (not during drag)
        if update_lcd and self.update_callback:
            self.update_callback()
            
    def move_without_callback(self, dx, dy, max_width=320, max_height=240, margin=5):
        """Move item without triggering update callback - used during dragging"""
        self.x = max(margin, min(self.x + dx, max_width - margin))
        self.y = max(margin, min(self.y + dy, max_height - margin))


    def update_text(self, text, trigger_callback=True):
        self.text = text
        if trigger_callback and self.update_callback:
            self.update_callback()


    def update_style(self, font_config=None, color=None):
        if font_config:
            self.font_config = font_config
            self._pil_font = None  # Force reload next draw
        if color:
            self.color = color
        if self.update_callback:
            self.update_callback()

    def apply_style(self):
        if self.update_callback:
            self.update_callback()

    def _centre_window(self, window, parent=None):
        """Centre a window on its parent or screen"""
        window.update_idletasks()

        # Get window dimensions
        window_width = window.winfo_width()
        window_height = window.winfo_height()

        # If parent exists, centre on parent
        if parent:
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()

            x = parent_x + (parent_width - window_width) // 2
            y = parent_y + (parent_height - window_height) // 2
        else:
            # Centre on screen
            screen_width = window.winfo_screenwidth()
            screen_height = window.winfo_screenheight()

            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2

        window.geometry(f"+{x}+{y}")

    def open_style_editor(self, parent=None):
        popup = tk.Toplevel(parent or self.canvas)
        popup.title(f"Edit Style: {self.tag}")
        popup.configure(bg="#2b2b2b")
        popup.columnconfigure(1, weight=1)  # make column 1 stretch

        # --- Font family
        tk.Label(popup, text="Font:", fg="white", bg="#2b2b2b").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        font_var = tk.StringVar(value=self.font_config.get("family", "DejaVu Sans"))

        # Get available font families
        try:
            available_families = list(font.families())
        except Exception:
            available_families = ["DejaVu Sans", "Liberation Sans", "Arial", "Helvetica"]

        font_combo = ttk.Combobox(popup, textvariable=font_var, values=available_families)
        font_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # --- Font size
        tk.Label(popup, text="Size:", fg="white", bg="#2b2b2b").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        size_var = tk.IntVar(value=self.font_config.get("size", 14))
        size_spin = tk.Spinbox(popup, from_=8, to=72, textvariable=size_var)
        size_spin.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # --- Style
        tk.Label(popup, text="Style:", fg="white", bg="#2b2b2b").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        style_var = tk.StringVar(value=self.font_config.get("style", "normal"))
        style_menu = ttk.Combobox(popup, textvariable=style_var, values=["normal", "bold", "italic", "bold italic"])
        style_menu.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # --- Color picker
        tk.Label(popup, text="Color:", fg="white", bg="#2b2b2b").grid(
            row=3, column=0, sticky="w", padx=5, pady=5
        )
        color_var = tk.StringVar(value=self.color)
        color_entry = tk.Entry(popup, textvariable=color_var)
        color_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        def pick_color(self, color_var, popup):
            color = colorchooser.askcolor(parent=popup, color=self.color)[1]
            if color:
                color_var.set(color)

        color_btn = tk.Button(popup, text="Pick", command=lambda: pick_color(self, color_var, popup))
        color_btn.grid(row=3, column=2, padx=5, pady=5)

        # --- Button frame
        button_frame = tk.Frame(popup, bg="#2b2b2b")
        button_frame.grid(row=4, column=0, columnspan=3, pady=10)

        def apply():
            self.font_config["family"] = font_var.get()
            self.font_config["size"] = size_var.get()
            self.font_config["style"] = style_var.get()
            self.color = color_var.get()
            self.update_style(self.font_config, self.color)

        def apply_and_close():
            apply()
            popup.destroy()

        # Buttons
        save_btn = tk.Button(button_frame, text="Apply", bg="#4CAF50", fg="white", activebackground="#45A049", activeforeground="white", underline=0, command=apply)
        save_btn.pack(side="left", padx=5)
        cancel_btn = tk.Button(button_frame, text="Cancel", bg="#f44336", fg="white", activebackground="#da190b", activeforeground="white", underline=0, command=popup.destroy)
        cancel_btn.pack(side="left", padx=5)
        reset_btn = tk.Button(button_frame, text="OK", bg="#008CBA", fg="white", activebackground="#007bb5", activeforeground="white", underline=0, command=apply_and_close)
        reset_btn.pack(side="left", padx=5)

        # Shortcuts
        popup.bind("<Control-a>", lambda e: apply_and_close())
        popup.bind("<Control-c>", lambda e: popup.destroy())
        popup.bind("<Control-o>", lambda e: reset_to_default())

        # Make modal and centre
        popup.transient(parent)
        self._centre_window(popup, parent)
        popup.update_idletasks()
        try:
            popup.grab_set()
        except Exception:
            # If grab fails (e.g., another modal is active), continue anyway
            pass
        popup.wait_window()

class ModernToggleSwitch(tk.Canvas):
    """Custom toggle switch widget matching TRCC style"""
    def __init__(self, parent, variable=None, width=50, height=24, **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0, **kwargs)
        self.variable = variable or tk.BooleanVar()
        self.width = width
        self.height = height

        # Colors matching TRCC
        self.bg_on = "#4CAF50"
        self.bg_off = "#555555"
        self.knob_color = "#FFFFFF"

        self.bind("<Button-1>", self.toggle)
        self.variable.trace_add("write", self.update_display)

        self.update_display()

    def toggle(self, event=None):
        self.variable.set(not self.variable.get())

    def update_display(self, *args):
        self.delete("all")

        # Background
        bg_color = self.bg_on if self.variable.get() else self.bg_off
        self.create_rounded_rect(2, 2, self.width-2, self.height-2, 
                                radius=self.height//2, fill=bg_color, outline="")

        # Knob
        knob_x = self.width - self.height//2 - 4 if self.variable.get() else self.height//2 + 2
        knob_radius = self.height//2 - 4
        self.create_oval(knob_x-knob_radius, self.height//2-knob_radius,
                        knob_x+knob_radius, self.height//2+knob_radius,
                        fill=self.knob_color, outline="")

    def create_rounded_rect(self, x1, y1, x2, y2, radius=10, **kwargs):
        points = []
        for x, y in [(x1, y1+radius), (x1, y1), (x1+radius, y1),
                     (x2-radius, y1), (x2, y1), (x2, y1+radius),
                     (x2, y2-radius), (x2, y2), (x2-radius, y2),
                     (x1+radius, y2), (x1, y2), (x1, y2-radius)]:
            points.extend([x, y])
        return self.create_polygon(points, smooth=True, **kwargs)

class ModernSectionFrame(tk.Frame):
    """Modern section frame with header and toggle"""
    def __init__(self, parent, title="", toggle_var=None, **kwargs):
        super().__init__(parent, bg="#2a2a2a", **kwargs)

        # Header frame
        header_frame = tk.Frame(self, bg="#2a2a2a", height=40)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        header_frame.pack_propagate(False)

        # Title
        title_label = tk.Label(header_frame, text=title, font=("Arial", 12, "bold"),
                              fg="#FFFFFF", bg="#2a2a2a")
        title_label.pack(side=tk.LEFT, pady=10)

        # Toggle switch
        if toggle_var:
            self.toggle = ModernToggleSwitch(header_frame, toggle_var, bg="#2a2a2a")
            self.toggle.pack(side=tk.RIGHT, pady=8)

        # Content frame
        self.content_frame = tk.Frame(self, bg="#2a2a2a")
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

class ModernModuleButton(tk.Frame):
    """Modern module button matching TRCC style"""
    def __init__(self, parent, text="", command=None, active=False, **kwargs):
        super().__init__(parent, bg="#2a2a2a", **kwargs)

        self.active = active
        self.command = command

        # Colors
        self.active_color = "#4A90E2"
        self.inactive_color = "#444444"
        self.hover_color = "#555555"

        # Button frame
        self.btn_frame = tk.Frame(self, bg=self.active_color if active else self.inactive_color,
                                 relief="flat", bd=1)
        self.btn_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Label
        self.label = tk.Label(self.btn_frame, text=text, font=("Arial", 9),
                             fg="#FFFFFF", bg=self.btn_frame['bg'])
        self.label.pack(expand=True, pady=8)

        # Bind events
        for widget in [self.btn_frame, self.label]:
            widget.bind("<Button-1>", self.on_click)
            widget.bind("<Enter>", self.on_enter)
            widget.bind("<Leave>", self.on_leave)

    def on_click(self, event):
        if self.command:
            self.command()

    def on_enter(self, event):
        if not self.active:
            self.btn_frame.config(bg=self.hover_color)
            self.label.config(bg=self.hover_color)

    def on_leave(self, event):
        if not self.active:
            self.btn_frame.config(bg=self.inactive_color)
            self.label.config(bg=self.inactive_color)

    def set_active(self, active):
        self.active = active
        color = self.active_color if active else self.inactive_color
        self.btn_frame.config(bg=color)
        self.label.config(bg=color)

    def set_text(self, text):
        """Update the label text."""
        self.label.config(text=text)

class LCDController:
    def __init__(self, root, config_file="lcd_config.json"):
        self.root = root
        self._update_queue = queue.Queue(maxsize=1)  # only keep latest request
        self._update_thread = threading.Thread(target=self._update_worker, daemon=True)
        self._update_thread.start()
        self.config_file = config_file
        self.draggable_items = {}
        self.background_image_id = None
        self.updating_gui = False
        self.active_module = None
        self.module_buttons = {}
        self.module_toggle_vars = {}
        self.info_poller = lcd_driver.CSystemInfoPoller()
        self.cached_metrics = {}
        self.config_manager = lcd_driver.ConfigManager(config_file)
        self.config_manager.load_config(config_file)
        self.cached_config = self.config_manager.get_config()
        self.last_metrics_update = datetime.now()
        self.metrics_update_interval = 1  # seconds (5 FPS)
        self.frame_times = deque(maxlen=60)
        self._frame_counter = 0
        self.is_obscured = False
        self.gui_should_update = True

        self.bg_manager = lcd_driver.get_background_manager()

        self._suppress_system_callback = False
        self._suppress_child_callback = False

        self.info_poller.start()
        self.setup_ui()
        self.setup_draggable_elements()
        self.start_data_updates()

    def setup_ui(self):
        self.root.title("Linux USB LCD Controller")
        self.root.configure(bg="#1e1e1e")
        self.root.minsize(1200, 600)

        # Configure style
        self.setup_styles()

        # Main container
        main_container = tk.Frame(self.root, bg="#1e1e1e")
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Left panel - Display
        self.setup_display_panel(main_container)

        # Right panel - Controls
        self.setup_primary_control_panel(main_container)
        self.setup_secondary_control_panel(main_container)

    def setup_styles(self):
        """Setup ttk styles for modern appearance"""
        style = ttk.Style()

        # Configure progress bar style
        style.theme_use('clam')
        style.configure("Modern.Horizontal.TProgressbar",
                       troughcolor='#444444',
                       background='#4CAF50',
                       borderwidth=0,
                       lightcolor='#4CAF50',
                       darkcolor='#4CAF50')

    def setup_display_panel(self, parent):
        """Setup left panel with LCD display and module buttons"""
        display_panel = tk.Frame(parent, bg="#1e1e1e")
        display_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))

        # LCD Display
        display_frame = tk.Frame(display_panel, bg="#2a2a2a", relief="solid", bd=1)
        display_frame.pack(pady=(0, 20))

        # Title
        tk.Label(display_frame, text="LCD Display", font=("Arial", 14, "bold"),
                fg="#FFFFFF", bg="#2a2a2a").pack(pady=(10, 5))

        self.lcd_canvas = tk.Canvas(display_frame, width=320, height=240,
                                   bg="#000000", highlightthickness=0)
        self.lcd_canvas.pack(padx=20, pady=(0, 10))

        # Bind events
        self.lcd_canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.lcd_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.lcd_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.lcd_canvas.bind("<Double-Button-1>", self.on_canvas_double_click)

        # Instructions
        instructions = tk.Label(display_frame,
                               text="• Click and drag to move items\n• Double-click to edit style",
                               fg="#CCCCCC", bg="#2a2a2a", justify="left")
        instructions.pack(pady=(0, 15))

        # Module buttons
        self.setup_module_buttons_modern(display_panel)

    def setup_module_buttons_modern(self, parent):
        """Setup modern module buttons grid"""
        module_frame = tk.Frame(parent, bg="#2a2a2a", relief="solid", bd=1)
        module_frame.pack(fill=tk.X)

        # Title
        tk.Label(module_frame, text="System Modules", font=("Arial", 14, "bold"),
                fg="#FFFFFF", bg="#2a2a2a").pack(pady=(10, 5))

        # Button grid
        button_grid = tk.Frame(module_frame, bg="#2a2a2a")
        button_grid.pack(padx=15, pady=(0, 15))
        
        config = self.config_manager.get_config()
        defaults = {
            "M1": "cpu_temp", "M2": "cpu_percent", "M3": "cpu_freq",
            "M4": "gpu_temp", "M5": "gpu_usage", "M6": "gpu_clock"
        }

        for i in range(1, 7):
            name = f"M{i}"
            metric = config.get(name, {}).get("metric", defaults[name])

            row = (i - 1) // 3
            col = (i - 1) % 3

            btn = ModernModuleButton(button_grid, text=f"{name}\n{metric}",
                                   command=lambda n=name: self.set_active_module(n))
            btn.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")

            # Configure grid weights
            button_grid.grid_rowconfigure(row, weight=1)
            button_grid.grid_columnconfigure(col, weight=1)

            self.module_buttons[name] = btn
    
    def refresh_module_buttons(self):
        """Update module button labels and states based on current config"""
        config = self.config_manager.get_config()

        for name, btn in self.module_buttons.items():
            entry = config.get(name, {})
            metric = entry.get("metric", name)
            enabled = entry.get("enabled", True)

            btn.set_text(f"{name}\n{metric}")
            btn.set_active(enabled)

    def refresh_system_toggles(self):
        """Update toggle states and module UI from current config without triggering traces."""
        config = self.config_manager.get_config()

        # Ensure suppression flags exist
        self._suppress_child_callback = getattr(self, "_suppress_child_callback", False)
        self._suppress_system_callback = getattr(self, "_suppress_system_callback", False)

        # Suppress child callbacks while we bulk set variables so we don't write back into config
        self._suppress_child_callback = True
        self._suppress_system_callback = True
        try:
            # Update all toggle BooleanVars tracked in module_toggle_vars
            for name, var in self.module_toggle_vars.items():
                conf = config.get(name, {})
                enabled = conf.get("enabled", True)
                # Set the var - trace handler will not run because we're suppressing
                var.set(bool(enabled))

                # Also update any corresponding module button appearance
                btn = self.module_buttons.get(name)
                if btn is not None:
                    # If you have label/metric info in config, update text too
                    metric = conf.get("metric", name)
                    # ModernModuleButton has set_text and set_active
                    try:
                        btn.set_text(f"{name}\n{metric}")
                    except Exception:
                        pass
                    try:
                        btn.set_active(bool(enabled))
                    except Exception:
                        pass


        finally:
            # Turn suppression off so normal user interactions work again
            self._suppress_child_callback = False
            self._suppress_system_callback = False

        # Recompute master toggle: set master to True if any child is True.
        if hasattr(self, "system_toggle"):
            new_master = any(v.get() for v in self.module_toggle_vars.values())
            # Avoid triggering the master callback while setting it
            self._suppress_system_callback = True
            try:
                self.system_toggle.set(new_master)
            finally:
                self._suppress_system_callback = False
    
        if hasattr(self, "update_datetime_controls"):
            try:
                self.update_datetime_controls()
            except Exception:
                pass
    
        # Finally request a redraw
        self.update_display_immediately()


    def reset_config(self):
        """Reset configuration to defaults"""
        import tkinter.messagebox as msgbox
        if msgbox.askyesno("Reset Configuration", 
                          "Are you sure you want to reset all settings to defaults?"):
            self.config_manager.load_config_from_defaults()
            self.refresh_module_buttons()
            self.refresh_system_toggles()
            self.setup_draggable_elements()  # Refresh display
            self.update_display_immediately()

    def _centre_window(self, window, parent=None):
        """Centre a window on its parent or screen"""
        window.update_idletasks()

        # Get window dimensions
        window_width = window.winfo_width()
        window_height = window.winfo_height()

        # If parent exists, centre on parent
        if parent:
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()

            x = parent_x + (parent_width - window_width) // 2
            y = parent_y + (parent_height - window_height) // 2
        else:
            # Centre on screen
            screen_width = window.winfo_screenwidth()
            screen_height = window.winfo_screenheight()

            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2

        window.geometry(f"+{x}+{y}")

    def setup_primary_control_panel(self, parent):
        """Setup middle panel with main controls"""
        control_panel = tk.Frame(parent, bg="#1e1e1e")
        control_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20)

        self.setup_custom_text_modern(control_panel)
        self.setup_datetime_modern(control_panel)
        self.setup_system_info_modern(control_panel)

    def setup_secondary_control_panel(self, parent):
        """Setup right panel with background and save controls"""
        secondary_panel = tk.Frame(parent, bg="#1e1e1e")
        secondary_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 0))
        
        # Background section
        self.setup_background_modern(secondary_panel)

        # Add some spacing
        spacer = tk.Frame(secondary_panel, bg="#1e1e1e", height=20)
        spacer.pack(fill=tk.X)

        # Save configuration section
        save_section = ModernSectionFrame(secondary_panel, "Actions")
        save_section.pack(fill=tk.X, pady=(0, 15))

        # Save button
        save_btn = tk.Button(save_section.content_frame, text="Save Configuration",
                            command=self.save_config,
                            bg="#4CAF50", fg="white", font=("Arial", 12, "bold"),
                            relief="flat", pady=12)
        save_btn.pack(fill=tk.X, padx=5, pady=5)

        reset_btn = tk.Button(save_section.content_frame, text="Reset to Defaults",
                         command=self.reset_config,
                         bg="#FF9800", fg="white", font=("Arial", 11),
                         relief="flat", pady=8)
        reset_btn.pack(fill=tk.X, padx=5, pady=(0, 5))


    def setup_custom_text_modern(self, parent):
        """Modern custom text section"""
        config = self.config_manager.get_config()
        custom_config = config.get("custom", {})

        self.toggle_custom = tk.BooleanVar(value=custom_config.get("enabled", True))
        self.module_toggle_vars["custom"] = self.toggle_custom
        section = ModernSectionFrame(parent, "Custom Text", self.toggle_custom)
        section.pack(fill=tk.X, pady=(0, 15))

        # Text input
        input_frame = tk.Frame(section.content_frame, bg="#2a2a2a")
        input_frame.pack(fill=tk.X, pady=5)

        tk.Label(input_frame, text="Text:", fg="#CCCCCC", bg="#2a2a2a").pack(anchor="w")

        self.custom_text_var = tk.StringVar(value=custom_config.get("text", ""))
        text_entry = tk.Entry(
            input_frame,
            textvariable=self.custom_text_var,
            bg="#444444",
            fg="#FFFFFF",
            relief="flat",
            font=("Arial", 10)
        )
        text_entry.pack(fill=tk.X, pady=(2, 0), ipady=5)

        # Debounced update implementation
        self._custom_text_debounce_job = None

        def on_custom_text_change(*args):
            if self._custom_text_debounce_job is not None:
                self.root.after_cancel(self._custom_text_debounce_job)
            self._custom_text_debounce_job = self.root.after(150, do_update)

        def do_update():
            new_text = self.custom_text_var.get()
            self.config_manager.update_config_value("custom.text", new_text)

            if "custom" in self.draggable_items:
                self.draggable_items["custom"].update_text(new_text)

            self.update_display_immediately()
            self._custom_text_debounce_job = None

        # Simple toggle handler like date/time
        def on_custom_toggle():
            self.config_manager.update_config_value("custom.enabled", self.toggle_custom.get())
            self.update_display_immediately()

        self.custom_text_var.trace_add("write", on_custom_text_change)
        self.toggle_custom.trace_add("write", lambda *args: on_custom_toggle())


    def setup_datetime_modern(self, parent):
        """Modern date/time section with independent toggles for date and time"""
        config = self.config_manager.get_config()

        # Outer section frame
        section = tk.Frame(parent, bg="#2a2a2a")
        section.pack(fill=tk.X, pady=(0, 15))

        # Title
        tk.Label(section, text="Date / Time", fg="#FFFFFF", bg="#2a2a2a",
                 font=("Arial", 14, "bold")).pack(anchor="w", pady=(5, 10))

        # --- Time controls ---
        time_config = config.get("time", {})
        self.time_toggle = tk.BooleanVar(value=time_config.get("enabled", True))
        time_row = tk.Frame(section, bg="#2a2a2a")
        time_row.pack(fill=tk.X, pady=5)

        time_toggle_btn = ModernToggleSwitch(time_row, self.time_toggle, bg="#2a2a2a")
        time_toggle_btn.pack(side="left", padx=(0, 10))
        tk.Label(time_row, text="Time", fg="#CCCCCC", bg="#2a2a2a").pack(side="left")

        self.time_format_var = tk.StringVar(value=time_config.get("format", "24h"))

        format_frame = tk.Frame(section, bg="#2a2a2a")
        format_frame.pack(fill=tk.X, pady=(2, 5))

        tk.Radiobutton(format_frame, text="24 Hour", variable=self.time_format_var,
                       value="24h", fg="#CCCCCC", bg="#2a2a2a", selectcolor="#444444",
                       activebackground="#2a2a2a", activeforeground="#FFFFFF",
                       command=self.on_time_format_change).pack(side="left", padx=(0, 15))

        tk.Radiobutton(format_frame, text="12 Hour", variable=self.time_format_var,
                       value="12h", fg="#CCCCCC", bg="#2a2a2a", selectcolor="#444444",
                       activebackground="#2a2a2a", activeforeground="#FFFFFF",
                       command=self.on_time_format_change).pack(side="left")

        # --- Date controls ---
        date_config = config.get("date", {})
        self.date_toggle = tk.BooleanVar(value=date_config.get("enabled", True))
        date_row = tk.Frame(section, bg="#2a2a2a")
        date_row.pack(fill=tk.X, pady=(10, 5))

        date_toggle_btn = ModernToggleSwitch(date_row, self.date_toggle, bg="#2a2a2a")
        date_toggle_btn.pack(side="left", padx=(0, 10))
        tk.Label(date_row, text="Date", fg="#CCCCCC", bg="#2a2a2a").pack(side="left")

        self.date_format_var = tk.StringVar(value=date_config.get("format", "%d-%m-%Y"))
        date_entry = tk.Entry(date_row, textvariable=self.date_format_var,
                              bg="#444444", fg="#FFFFFF", relief="flat", font=("Arial", 10))
        date_entry.pack(fill=tk.X, pady=(2, 0), ipady=5)

        self.date_preview = tk.Label(date_row, text="", fg="#4CAF50", bg="#2a2a2a")
        self.date_preview.pack(anchor="w", pady=(2, 0))

        # --- Bind events ---
        def on_time_toggle(*args):
            self.config_manager.update_config_value("time.enabled", self.time_toggle.get())
            self.update_display_immediately()

        def on_date_toggle(*args):
            self.config_manager.update_config_value("date.enabled", self.date_toggle.get())
            self.update_display_immediately()

        self.time_toggle.trace_add("write", on_time_toggle)
        self.module_toggle_vars["time"] = self.time_toggle
        self.module_toggle_vars["date"] = self.date_toggle
        self.date_toggle.trace_add("write", on_date_toggle)
        self.date_format_var.trace_add("write", self.on_date_format_change)

        self.update_date_preview()


    def setup_system_info_modern(self, parent):
        """Compact system info section with master toggle, CPU/GPU labels, and M1–M6 switches"""
        config = self.config_manager.get_config()

        # Master toggle
        self.system_toggle = tk.BooleanVar(value=True)
        section = ModernSectionFrame(parent, "System Info", self.system_toggle)
        section.pack(fill=tk.X, pady=(0, 15))

        # Track toggle vars
        if not hasattr(self, 'module_toggle_vars'):
            self.module_toggle_vars = {}    
        def add_toggle(frame, tag, default_enabled=True):
            """Helper to add a toggle for cpu_label, gpu_label, or M1–M6"""
            conf = config.get(tag, {})
            var = tk.BooleanVar(value=conf.get("enabled", default_enabled))
            self.module_toggle_vars[tag] = var

            # Label + toggle
            label = tk.Label(frame, text=tag.upper(), fg="#CCCCCC",
                             bg="#2a2a2a", font=("Arial", 10))
            label.pack(side="left", padx=(0, 5))
    
            toggle = ModernToggleSwitch(frame, var, bg="#2a2a2a")
            toggle.pack(side="left", padx=(0, 15), pady=5)

            # Bind: update config + preview immediately
            var.trace_add("write", lambda *args, n=tag: on_child_toggle(n))

        # --- Handlers ---
        def on_system_toggle(*args):
            """Flip all children when master toggled by user"""
            if getattr(self, "_suppress_system_callback", False):
                return
            enabled = self.system_toggle.get()
            self._suppress_child_callback = True
            try:
                for name, var in self.module_toggle_vars.items():
                    var.set(enabled)
                    self.on_module_toggle(name)
            finally:
                self._suppress_child_callback = False
            self.update_display_immediately()

        def on_child_toggle(name, *args):
            """Child toggle changed → update config + recompute master"""
            if getattr(self, "_suppress_child_callback", False):
                return
            self.on_module_toggle(name)
            # Master ON if any child ON, OFF if all children OFF
            new_master = any(v.get() for v in self.module_toggle_vars.values())
            if new_master != self.system_toggle.get():
                self._suppress_system_callback = True
                try:
                    self.system_toggle.set(new_master)
                finally:
                    self._suppress_system_callback = False
            self.update_display_immediately()

        # --- CPU row ---
        cpu_row = tk.Frame(section.content_frame, bg="#2a2a2a")
        cpu_row.pack(fill=tk.X, pady=5)
        add_toggle(cpu_row, "cpu_label")
        for i in range(1, 4):
            add_toggle(cpu_row, f"M{i}")

        # --- GPU row ---
        gpu_row = tk.Frame(section.content_frame, bg="#2a2a2a")
        gpu_row.pack(fill=tk.X, pady=5)
        add_toggle(gpu_row, "gpu_label")
        for i in range(4, 7):
            add_toggle(gpu_row, f"M{i}")

        # Hook up master toggle
        self.system_toggle.trace_add("write", on_system_toggle)

        # Sync master to initial child state
        self._suppress_system_callback = True
        try:
            self.system_toggle.set(any(v.get() for v in self.module_toggle_vars.values()))
        finally:
            self._suppress_system_callback = False


    def setup_background_modern(self, parent):
        """Modern background section"""
        config = self.config_manager.get_config()

        section = ModernSectionFrame(parent, "Background")
        section.pack(fill=tk.X, pady=(0, 15))

        # Current background
        self.bg_path_var = tk.StringVar(value=config.get("background_path", "None"))

        path_frame = tk.Frame(section.content_frame, bg="#2a2a2a")
        path_frame.pack(fill=tk.X, pady=5)

        tk.Label(path_frame, text="Current:", fg="#CCCCCC", bg="#2a2a2a").pack(anchor="w")

        path_display = tk.Label(path_frame, textvariable=self.bg_path_var,
                               fg="#4CAF50", bg="#2a2a2a", font=("Arial", 9),
                               wraplength=250, justify="left")
        path_display.pack(anchor="w", pady=(2, 0))

        # Buttons
        btn_frame = tk.Frame(section.content_frame, bg="#2a2a2a")
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        browse_btn = tk.Button(btn_frame, text="Browse...",
                              command=self.browse_background,
                              bg="#4CAF50", fg="white", relief="flat", font=("Arial", 10))
        browse_btn.pack(side="left", padx=(0, 10), ipady=3)

        clear_btn = tk.Button(btn_frame, text="Clear",
                             command=self.clear_background,
                             bg="#f44336", fg="white", relief="flat", font=("Arial", 10))
        clear_btn.pack(side="left", ipady=3)

    # Event handlers
    def on_time_format_change(self):
        fmt = self.time_format_var.get()
        self.config_manager.update_config_value("time.format", fmt)
        if "time" in self.draggable_items:
            if fmt == "24h":
                time_text = datetime.now().strftime("%H:%M")
            else:
                time_text = datetime.now().strftime("%I:%M %p")
            self.draggable_items["time"].update_text(time_text)
        self.update_display_immediately()

    def on_date_format_change(self, *args):
        fmt = self.date_format_var.get()
        self.config_manager.update_config_value("date.format", fmt)
        if "date" in self.draggable_items:
            try:
                date_text = datetime.now().strftime(fmt)
                self.draggable_items["date"].update_text(date_text)
            except Exception:
                self.draggable_items["date"].update_text("Invalid Format")
        self.update_date_preview()
        self.update_display_immediately()

    def update_date_preview(self):
        fmt = self.date_format_var.get()
        try:
            preview_text = datetime.now().strftime(fmt)
            self.date_preview.config(text=f"Preview: {preview_text}")
        except Exception:
            self.date_preview.config(text="Preview: Invalid format")

    def on_module_toggle(self, name):
        enabled = self.module_toggle_vars[name].get()
        self.config_manager.update_config_value(f"{name}.enabled", enabled)
        self.update_display_immediately()

    def browse_background(self):
        filename = filedialog.askopenfilename(
        title="Select Background",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"),
            ("Video files", "*.mp4 *.avi *.mov *.mkv"),
            ("All files", "*.*"),
        ]
        )

        if filename:
            self.bg_path_var.set(os.path.basename(filename))
            self.config_manager.update_config_value("background_path", filename)
            self.update_display_immediately()

    def clear_background(self):
        self.bg_path_var.set("None")
        self.config_manager.update_config_value("background_path", None)
        self.update_display_immediately()

    def set_active_module(self, module_name):
        # Deactivate previous
        if self.active_module and self.active_module in self.module_buttons:
            self.module_buttons[self.active_module].set_active(False)

        # Activate new
        self.active_module = module_name
        self.module_buttons[module_name].set_active(True)

        self.open_module_selector(module_name)

    def open_module_selector(self, module_name):
        popup = tk.Toplevel(self.root)
        popup.title(f"Select metric for {module_name}")
        popup.configure(bg="#2b2b2b")

        # Make transient (grab_set will be called at the end)
        popup.transient(self.root)

        metrics = self.info_poller.get_available_metrics()

        listbox = tk.Listbox(popup, bg="#333", fg="white", selectbackground="#4CAF50")
        for m in metrics:
            listbox.insert(tk.END, m)
        listbox.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        def apply_selection():
            selection = listbox.get(tk.ACTIVE)
            config = self.config_manager.get_config()
            self.config_manager.update_config_value(f"{module_name}.metric", selection)
            # Update button label
            self.module_buttons[module_name].label.config(text=f"{module_name}: {selection}")
            self.update_display_immediately()
            popup.destroy()

        btn_frame = tk.Frame(popup, bg="#2b2b2b")
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="✓ OK", command=apply_selection,
                  bg="green", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="✗ Cancel", command=popup.destroy,
                  bg="red", fg="white").pack(side=tk.LEFT, padx=5)

        # Centre and make modal after window is ready
        self._centre_window(popup, self.root)
        popup.update_idletasks()
        try:
            popup.grab_set()
        except Exception:
            # If grab fails (e.g., another modal is active), continue anyway
            pass

    def setup_draggable_elements(self):
        config = self.config_manager.get_config()

        self.draggable_items.clear()

        for tag, conf in config.items():
            if not isinstance(conf, dict):
                continue  # Skip settings like background_path

            x, y = conf.get("x", 10), conf.get("y", 10)
            font_config = conf.get("font", {"family": "DejaVu Sans", "size": 20, "style": "normal"})
            color = conf.get("color", "#FFFFFF")

            if tag == "time":
                time_format = conf.get("format", "24h")
                if time_format == "24h":
                    text = datetime.now().strftime("%H:%M")
                else:
                    text = datetime.now().strftime("%I:%M %p")
            elif tag == "date":
                date_format = conf.get("format", "%d-%m-%Y")  # This should use saved format
                try:
                    text = datetime.now().strftime(date_format)
                except Exception:
                    text = datetime.now().strftime("%d-%m-%Y")

            if tag.startswith("M"):
                text = self.get_display_text_for_metric(conf.get("metric", "cpu_temp"), {})
            elif tag in ("cpu_label", "gpu_label", "custom"):
                text = conf.get("text", tag)

            self.draggable_items[tag] = DraggableTextPillow(
                tag, text, x, y, font_config, color, self.render_lcd_image
            )
            
    def safe_number(self, val, default=0):
        try:
            return float(val) if val is not None else default
        except Exception:
            return default

    def get_display_text_for_metric(self, metric, info):
        # Handle special cases first (non-numeric or special formatting)
        if metric == "time":
            return datetime.now().strftime("%H:%M")
        elif metric == "date":
            return datetime.now().strftime("%d-%m-%Y")
        elif metric == "custom":
            return self.config_manager.get_config().get("custom_text", "Hello")

        # Handle all numeric metrics with appropriate units and formatting
        value = self.safe_number(info.get(metric, 0))

        # Define formatting rules for different metric types
        metric_formats = {
            # Temperature metrics
            "cpu_temp": f"{value:.0f}°C",
            "gpu_temp": f"{value:.0f}°C",

            # Frequency metrics  
            "cpu_freq": f"{value:.0f}MHz",
            "gpu_clock": f"{value:4.0f}MHz",

            # Percentage metrics
            "cpu_percent": f"{value:.0f}%",
            "gpu_usage": f"{value:.0f}%",
            "mem_percent": f"RAM {value:.0f}%",
            "disk_percent": f"DISK {value:.0f}%",

            # Memory metrics
            "mem_used_gb": f"RAM {value:.1f}GB",

            # Disk metrics
            "disk_free_gb": f"DISK {value:.0f}GB free",

            # Fan metrics
            "gpu_fan": f"{value:.0f}RPM",

            # Count metrics
            "cpu_count": f"{value:.0f} cores",

        }

        # Return formatted value if we have a rule, otherwise generic format
        return metric_formats.get(metric, f"{metric.replace('_', ' ').title()}: {value:.1f}")

    def sync_items_to_config(self):
        config = self.config_manager.get_config()
        for tag, item in self.draggable_items.items():
            conf = config.setdefault(tag, {})
            conf.update({
                "x": item.x,
                "y": item.y,
                "font": item.font_config,
                "color": item.color,
                "enabled": True,
            })
            if tag in ("cpu_label", "gpu_label", "custom"):
                conf["text"] = item.text

        # At this point _config is fully up to date in memory

    def on_canvas_press(self, event):
        self.dragging_item = None
        config = self.config_manager.get_config()

        # Only check visible items
        for tag, item in reversed(list(self.draggable_items.items())):
            if self.is_item_visible(tag, config) and item.contains(event.x, event.y):
                self.dragging_item = item
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                item.dragging = True  # Set dragging state
                break

    def on_canvas_drag(self, event):
        if getattr(self, 'dragging_item', None):
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y

            # Move item but DON'T update LCD during drag
            self.dragging_item.move(dx, dy, update_lcd=False)
            self.drag_start_x = event.x
            self.drag_start_y = event.y

            # Only update the canvas preview, not the LCD device
            self.update_canvas_preview_only()

    def on_canvas_release(self, event):
        if getattr(self, 'dragging_item', None):
            tag = self.dragging_item.tag

            # Save final position
            self.config_manager.update_config_value(f"{tag}.x", int(self.dragging_item.x))
            self.config_manager.update_config_value(f"{tag}.y", int(self.dragging_item.y))
            self.dragging_item.dragging = False

            # NOW update the LCD device with final position
            self.update_display_immediately()

            self.dragging_item = None

    def update_canvas_preview_only(self):
        """Update only the canvas preview during drag, without USB communication"""
        try:
            config = self.config_manager.get_config()

            bg_path = config.get("background_path") or ""
            bg_img = self.bg_manager.get_background_bytes(bg_path)
            if bg_img is not None:
                img = Image.frombytes("RGB", (320, 240), bg_img)
            else:
                img = Image.new("RGB", (320, 240), "black")
            draw = ImageDraw.Draw(img)

            # Draw all visible items
            for tag, item in self.draggable_items.items():
                if self.is_item_visible(tag, config):
                    item.draw(draw)

            # Update only the canvas display, skip USB
            self.draw_preview(img)

        except Exception as e:
            print(f"Error updating canvas preview: {e}")


    def on_canvas_double_click(self, event):
        config = self.config_manager.get_config()
        
        for tag, item in reversed(list(self.draggable_items.items())):
            if self.is_item_visible(tag, config) and item.contains(event.x, event.y):
                item.open_style_editor(self.root)
                break

    def is_item_visible(self, tag, config=None):
        """Check if an item should be visible based on config"""
        if config is None:
            config = self.config_manager.get_config()

        return config.get(tag, {}).get("enabled", True)

    def render_background(self):
        """Fetch and return just the background image (PIL.Image)."""
        bg_path = self.config_manager.get_config().get("background_path") or ""
        bg_img = self.bg_manager.get_background_bytes(bg_path)
    
        if bg_img and len(bg_img) == 320 * 240 * 3:
            img = Image.frombytes("RGB", (320, 240), bg_img)
        else:
            img = Image.new("RGB", (320, 240), "black")

        return img


    def render_overlays(self, img):
        """Draw metrics, text, and other overlays onto an existing image."""
        draw = ImageDraw.Draw(img)

        config = self.config_manager.get_config()
        info = self.info_poller.get_info()
        now = datetime.now()

        text_updates = {}

        # --- Time ---
        time_conf = config.get("time", {})
        if time_conf.get("enabled", True):
            tf = time_conf.get("format", "24h")
            if tf == "24h":
                text_updates["time"] = now.strftime("%H:%M")
            else:
                text_updates["time"] = now.strftime("%I:%M %p")

        # --- Date ---
        date_conf = config.get("date", {})
        if date_conf.get("enabled", True):
            fmt = date_conf.get("format", "%d-%m-%Y")
            try:
                text_updates["date"] = now.strftime(fmt)
            except Exception:
                text_updates["date"] = now.strftime("%d-%m-%Y")

        # --- Custom text (now same pattern as date/time) ---
        custom_conf = config.get("custom", {})
        if custom_conf.get("enabled", True):  # Same default as others
            text_updates["custom"] = custom_conf.get("text", "LINUX")

        # --- CPU/GPU labels ---
        for lbl in ("cpu_label", "gpu_label"):
            conf = config.get(lbl, {})
            if conf.get("enabled", True):
                text_updates[lbl] = conf.get("text", lbl.upper())

        # --- Modules ---
        for module_name, module_conf in ((k, v) for k, v in config.items() if k.startswith("M")):
            if not module_conf.get("enabled", True):
                continue
            metric = module_conf.get("metric", "")
            text = self.get_display_text_for_metric(metric, info)
            text_updates[module_name] = text

        # Push updates to draggable items
        for tag, text in text_updates.items():
            if tag in self.draggable_items and text is not None:
                self.draggable_items[tag].update_text(text, trigger_callback=False)

        # Draw all items
        for tag, item in self.draggable_items.items():
            if self.is_item_visible(tag, config):
                item.draw(draw)

        return img

    def render_lcd_image(self):
        """Build and send image to device (heavy, no Tkinter)."""
        img = self.render_background()  # always fetch current video frame
        config = self.cached_config

        # --- metrics caching ---
        now = datetime.now()
        elapsed = (now - self.last_metrics_update).total_seconds()
        if elapsed >= self.metrics_update_interval:
            info = self.info_poller.get_info()
            self.cached_config = self.config_manager.get_config()
            config = self.cached_config
            text_updates = {}

            # --- Time ---
            time_conf = config.get("time", {})
            if time_conf.get("enabled", True):
                tf = time_conf.get("format", "24h")
                text_updates["time"] = now.strftime("%H:%M") if tf=="24h" else now.strftime("%I:%M %p")

            # --- Date ---
            date_conf = config.get("date", {})
            if date_conf.get("enabled", True):
                fmt = date_conf.get("format", "%d-%m-%Y")
                try:
                    text_updates["date"] = now.strftime(fmt)
                except Exception:
                    text_updates["date"] = now.strftime("%d-%m-%Y")

            # --- Custom text ---
            custom_conf = config.get("custom", {})
            if custom_conf.get("enabled", True):
                text_updates["custom"] = custom_conf.get("text", "")

            # --- CPU/GPU labels ---
            for lbl in ("cpu_label", "gpu_label"):
                conf = config.get(lbl, {})
                if conf.get("enabled", True):
                    text_updates[lbl] = conf.get("text", lbl.upper())

            # --- Modules ---
            for module_name, module_conf in ((k, v) for k, v in config.items() if k.startswith("M")):
                if module_conf.get("enabled", True):
                    metric = module_conf.get("metric", "")
                    text_updates[module_name] = self.get_display_text_for_metric(metric, info)

            self.cached_metrics = text_updates
            self.last_metrics_update = now

    # Draw cached metrics
        draw = ImageDraw.Draw(img)
        # Push updates to draggable items
        for tag, text in self.cached_metrics.items():
            if tag in self.draggable_items and text is not None:
                self.draggable_items[tag].update_text(text, trigger_callback=False)

        for tag, item in self.draggable_items.items():
            if self.is_item_visible(tag, config):
                item.draw(draw)
        try:
            lcd_driver.update_lcd_image(img.tobytes())
        except:
            exit(1)
        return img

    def draw_preview(self, img):
        """Update preview canvas (must be main thread)."""
        self.tk_lcd_image = ImageTk.PhotoImage(img)
        self.lcd_canvas.delete("lcd_image")
        self.lcd_canvas.create_image(0, 0, image=self.tk_lcd_image, anchor="nw", tags="lcd_image")

    def save_config(self):
        self.config_manager.save_config(self.config_file)
        #print(f"Configuration saved to {self.config_file}")

    def update_display_immediately(self):
        """Request a display update in the background thread."""
        try:
            # drop old request if queue is full
            if self._update_queue.full():
                self._update_queue.get_nowait()
            self._update_queue.put_nowait(True)
        except queue.Full:
            pass


    def _update_worker(self):
        while True:
            self._update_queue.get()
            try:
                start = time.perf_counter()

                img = self.render_lcd_image()  # heavy (PIL + USB)

                # Only schedule the Tk preview update if GUI should be updating
                try:
                    should_update = getattr(self, "gui_should_update", True)

                    if getattr(self, "root", None) is not None and should_update:
                        self.root.after(0, lambda i=img: self.draw_preview(i))  # GUI-safe
                    # else: window not focused/minimized, skip GUI update to save resources
                except Exception as e:
                    # If something odd happens, still avoid crashing the worker
                    print(f"[worker] preview scheduling skipped due to: {e}")

                end = time.perf_counter()
                self.frame_times.append(end)
                self._frame_counter += 1

            except Exception:
                import traceback
                traceback.print_exc()

    def save_config(self):
        self.sync_items_to_config()
        self.config_manager.save_config(self.config_file)

    def start_data_updates(self):
        self.is_obscured = False
        self.is_minimized = False
        self.has_focus = True
        self.is_mapped = True

        # Bind multiple state detection events
        self.root.bind('<Visibility>', self.on_visibility_change)
        self.root.bind('<FocusIn>', self.on_focus_in)
        self.root.bind('<FocusOut>', self.on_focus_out)
        self.root.bind('<Map>', self.on_map)
        self.root.bind('<Unmap>', self.on_unmap)

        # Start the LCD update timer (always 40ms)
        def lcd_update():
            if not self.updating_gui:
                try:
                    self.update_display_immediately()
                except Exception as e:
                    print(f"LCD update error: {e}")

            # Always schedule next LCD update at 40ms
            self.root.after(40, lcd_update)

        previous_interval = None
        last_slow_time = 0  # Track when we last went to slow refresh
        first_poll = True  # Flag for first poll

        def gui_poll():
            nonlocal previous_interval, last_slow_time, first_poll
            try:
                # Check focus
                focus_result = self.root.tk.call("focus")
                name = str(focus_result) if focus_result else "None"
                current_time = time.time()

                # On first poll, assume window is visible and focused
                if first_poll:
                    first_poll = False
                    interval = 40
                    self.gui_should_update = True
                # Determine if we should use slow or fast polling and whether to update GUI
                elif self.is_obscured:
                    # Window is fully obscured
                    interval = 200
                    self.gui_should_update = False
                    last_slow_time = current_time
                elif name == "None":
                    interval = 200  # Unfocused/minimized window
                    self.gui_should_update = False
                    last_slow_time = current_time
                elif name.startswith(".__tk_"):
                    interval = 200  # Filedialog or transient
                    self.gui_should_update = True  # Keep updating for dialogs
                    last_slow_time = current_time
                else:
                    # If we recently switched to slow polling, stay slow for a bit
                    if current_time - last_slow_time < 2.0:  # 2 second grace period
                        interval = 200
                        self.gui_should_update = False
                    else:
                        interval = 40
                        self.gui_should_update = True
            except Exception as e:
                interval = 200
                self.gui_should_update = False
                print(f"Exception in gui_poll: {e}")

            if interval != previous_interval:
                previous_interval = interval

            self.root.after(interval, gui_poll)

        # Start both timers
        lcd_update()
        gui_poll()

    def on_visibility_change(self, event):
        """Called when window visibility changes"""
        # VisibilityUnobscured = 0, VisibilityPartiallyObscured = 1, VisibilityFullyObscured = 2
        if hasattr(event, 'state'):
            if event.state == 'VisibilityFullyObscured':
                self.is_obscured = True
            else:
                self.is_obscured = False
        else:
            # Fallback: check the string representation
            self.is_obscured = (str(event.state) == 'VisibilityFullyObscured')

    def on_focus_in(self, event):
        """Called when window gains focus"""
        # Only set focus if the event is for the root window
        if event.widget == self.root:
            self.has_focus = True

    def on_focus_out(self, event):
        """Called when window loses focus"""
        # Only clear focus if the event is for the root window
        if event.widget == self.root:
            self.has_focus = False

    def on_map(self, event):
        """Called when window is mapped (shown)"""
        # Compare widget string representation - root is typically "."
        widget_str = str(event.widget)
        if widget_str == ".":
            print("[on_map] Setting is_mapped=True, is_minimized=False")
            self.is_mapped = True
            self.is_minimized = False

    def on_unmap(self, event):
        """Called when window is unmapped (hidden/minimized)"""
        # Compare widget string representation - root is typically "."
        widget_str = str(event.widget)
        if widget_str == ".":
            self.is_mapped = False
            self.is_minimized = True


if __name__ == "__main__":

    if not lcd_driver.init_dev():
        messagebox.showerror("USB LCD", "Failed to initialize USB device")
        exit(1)

    root = tk.Tk()

    app = LCDController(root)
    try:
        root.mainloop()
    finally:
        # Clean up on exit
        lcd_driver.cleanup_dev()
