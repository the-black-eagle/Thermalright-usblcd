import os
import sys
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


class BackgroundSelector(tk.Frame):
    def __init__(self, parent, config_manager, config_wrapper, apply_theme_callback, apply_video_callback, configfile,
                 browse_image_callback=None, browse_video_callback=None, reset_config_callback=None):
        super().__init__(parent, bg="#2b2b2b", highlightbackground="#444444", 
                        highlightthickness=1, relief="solid")
        self.config_manager = config_manager
        self.config_wrapper = config_wrapper
        self.configfile = configfile
        self.apply_theme_callback = apply_theme_callback
        self.apply_video_callback = apply_video_callback
        self.browse_image_callback = browse_image_callback
        self.browse_video_callback = browse_video_callback
        self.reset_config_callback = reset_config_callback
        data_dirs = self.get_data_directories()
        self.images_dir = data_dirs['images']
        self.videos_dir = data_dirs['videos']

        # Track selected items
        self.selected_theme_frame = None
        self.selected_video_frame = None
        self.theme_frames = {}  # path -> frame mapping
        self.video_frames = {}  # path -> frame mapping

        # Title
        title_label = tk.Label(self, text="Media Selector", 
                              bg="#2b2b2b", fg="white", 
                              font=("Arial", 14, "bold"))
        title_label.pack(pady=(10, 5))

        # Notebook (tabs for themes and videos)
        style = ttk.Style()
        style.theme_use('default')
        style.configure('Dark.TNotebook', background='#2b2b2b', borderwidth=0)
        style.configure('Dark.TNotebook.Tab', background='#3c3c3c', foreground='white',
                       padding=[10, 5], borderwidth=1)
        style.map('Dark.TNotebook.Tab',
                 background=[('selected', '#4CAF50')],
                 foreground=[('selected', 'white')])
        
        notebook = ttk.Notebook(self, style='Dark.TNotebook')
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        theme_tab = tk.Frame(notebook, bg="#2b2b2b")
        video_tab = tk.Frame(notebook, bg="#2b2b2b")
        notebook.add(theme_tab, text="Themes")
        notebook.add(video_tab, text="Videos")

        # --- Themes tab ---
        self.create_preview_grid(
            parent=theme_tab,
            base_dir=self.images_dir,
            img_size=(120, 90),
            on_click=self.on_theme_click,
            is_video=False
        )

        # --- Videos tab ---
        self.create_preview_grid(
            parent=video_tab,
            base_dir=self.videos_dir,
            img_size=(120, 120),
            on_click=self.on_video_click,
            is_video=True
        )

        # --- Bottom buttons ---
        bottom_frame = tk.Frame(self, bg="#2b2b2b")
        bottom_frame.pack(fill=tk.X, pady=10, padx=10)

        # Button width (in characters)
        button_width = 18

        # First row - Browse buttons
        browse_frame = tk.Frame(bottom_frame, bg="#2b2b2b")
        browse_frame.pack(fill=tk.X, pady=(0, 5))

        # Store button references
        self.browse_image_btn = tk.Button(browse_frame, text="Browse Image",
                                         width=button_width,
                                         bg="#2196F3", fg="white", relief="flat",
                                         font=("Arial", 10, "bold"),
                                         activebackground="#1976D2",
                                         command=lambda: self._browse_with_reset(
                                             self.browse_image_btn, 
                                             self.browse_image_callback
                                         ) if self.browse_image_callback else None)
        self.browse_image_btn.pack(side="left", expand=True, padx=5, pady=5)

        self.browse_video_btn = tk.Button(browse_frame, text="Browse Video",
                                         width=button_width,
                                         bg="#9C27B0", fg="white", relief="flat",
                                         font=("Arial", 10, "bold"),
                                         activebackground="#7B1FA2",
                                         command=lambda: self._browse_with_reset(
                                             self.browse_video_btn,
                                             self.browse_video_callback
                                         ) if self.browse_video_callback else None)
        self.browse_video_btn.pack(side="left", expand=True, padx=5, pady=5)

        # Second row - Save and Reset buttons
        action_frame = tk.Frame(bottom_frame, bg="#2b2b2b")
        action_frame.pack(fill=tk.X)

        save_btn = tk.Button(action_frame, text="Save Configuration", 
                            width=button_width,
                            bg="#4CAF50", fg="white", relief="flat",
                            font=("Arial", 10, "bold"),
                            activebackground="#45a049",
                            command=self.save_config)
        save_btn.pack(side="left", expand=True, padx=5, pady=5)

        default_btn = tk.Button(action_frame, text="Reset to Defaults", 
                               width=button_width,
                               bg="#FF9800", fg="white", relief="flat",
                               font=("Arial", 10, "bold"),
                               activebackground="#e68900",
                               command=self.reset_defaults)
        default_btn.pack(side="left", expand=True, padx=5, pady=5)


    def _browse_with_reset(self, button, callback):
        """Reset button state after closing file dialog"""
        # Call the callback
        if callable(callback):
            callback()

        # Ensure button is back to normal after dialog closes
        if button['state'] == "active":
            button['state'] = "normal"


    def get_data_directories(self):
        """
        Get the correct paths for images and videos based on install location
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Possible locations for data
        locations = [
            # 1. Development: build directory with symlink
            os.path.join(script_dir, 'USBLCD'),
            # 2. Installed via .deb: /usr/share/tr-driver/USBLCD
            '/usr/share/tr-driver/USBLCD',
            # 3. AppImage/PyInstaller: relative to executable
            os.path.join(getattr(sys, '_MEIPASS', script_dir), 'USBLCD'),
            # 4. Relative to script in lib/tr-driver
            os.path.join(script_dir, '..', '..', 'share', 'tr-driver', 'USBLCD'),
        ]

        # Find first location that exists
        for location in locations:
            images_dir = os.path.join(location, 'images')
            videos_dir = os.path.join(location, 'videos')
            
            if os.path.exists(images_dir) or os.path.exists(videos_dir):
                return {
                    'images': os.path.abspath(images_dir) if os.path.exists(images_dir) else None,
                    'videos': os.path.abspath(videos_dir) if os.path.exists(videos_dir) else None
                }

        # Fallback
        print(f"WARNING: Could not find USBLCD data directory, checked: {locations}")
        return {'images': None, 'videos': None}


    def create_preview_grid(self, parent, base_dir, img_size, on_click, is_video=False):
        # Container frame
        container = tk.Frame(parent, bg="#2b2b2b")
        container.pack(fill=tk.BOTH, expand=True)

        # Calculate required width for 5 columns
        max_cols = 5
        canvas_width = max_cols * (img_size[0] + 10) + 30

        loading_label = tk.Label(container, text="Loading thumbnails...", 
                                bg="#2b2b2b", fg="white", font=("Arial", 12))
        loading_label.pack(expand=True)
        container.update()

        # Canvas with scrollbar - set minimum width
        canvas = tk.Canvas(container, bg="#2b2b2b", highlightthickness=0, width=canvas_width)

        # Style the scrollbar
        style = ttk.Style()
        style.configure("Dark.Vertical.TScrollbar",
                       background="#3c3c3c",
                       troughcolor="#2b2b2b",
                       borderwidth=0,
                       arrowcolor="white")

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview,
                                 style="Dark.Vertical.TScrollbar")

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill=tk.BOTH, expand=True)

        canvas.configure(yscrollcommand=scrollbar.set)

        # Frame inside canvas
        frame = tk.Frame(canvas, bg="#2b2b2b")
        canvas_window = canvas.create_window((0, 0), window=frame, anchor="nw")

        row, col = 0, 0
        loading_label.destroy()


        # Mouse wheel scroll function
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


        def on_mouse_enter(event):
            # Bind mouse wheel when mouse enters
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))


        def on_mouse_leave(event):
            # Unbind when mouse leaves
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        # Bind enter/leave events to canvas and frame
        canvas.bind("<Enter>", on_mouse_enter)
        canvas.bind("<Leave>", on_mouse_leave)
        frame.bind("<Enter>", on_mouse_enter)
        frame.bind("<Leave>", on_mouse_leave)

        if is_video:
            # For videos: look for PNG files directly in base_dir
            for filename in sorted(os.listdir(base_dir)):
                if not filename.lower().endswith('.png'):
                    continue
                path = os.path.join(base_dir, filename)
                try:
                    img = Image.open(path)
                    img = img.resize(img_size, Image.Resampling.BILINEAR)
                    photo = ImageTk.PhotoImage(img)

                    # Frame around image for border effect
                    img_frame = tk.Frame(frame, bg="#444444", padx=2, pady=2)
                    img_frame.grid(row=row, column=col, padx=5, pady=5)

                    label = tk.Label(img_frame, image=photo, bg="#2b2b2b", cursor="hand2")
                    label.image = photo  # prevent GC
                    label.pack()

                    # Store frame reference and bind click with highlight
                    self.video_frames[path] = img_frame
                    label.bind("<Button-1>", lambda e, p=path, f=img_frame: self.on_video_click_with_highlight(p, f))

                    # Bind mouse enter to labels too
                    label.bind("<Enter>", on_mouse_enter)
                    img_frame.bind("<Enter>", on_mouse_enter)

                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1
                except Exception as e:
                    print(f"Error loading {path}: {e}")
        else:
            # For themes: look for Theme.png in subdirectories
            for subdir in sorted(os.listdir(base_dir)):
                path = os.path.join(base_dir, subdir, "Theme.png")
                if not os.path.exists(path):
                    continue
                try:
                    img = Image.open(path)
                    #img = img.thumbnail(img_size, Image.Resampling.BILINEAR)
                    photo = ImageTk.PhotoImage(img)

                    # Frame around image for border effect
                    img_frame = tk.Frame(frame, bg="#444444", padx=2, pady=2)
                    img_frame.grid(row=row, column=col, padx=5, pady=5)

                    label = tk.Label(img_frame, image=photo, bg="#2b2b2b", cursor="hand2")
                    label.image = photo  # prevent GC
                    label.pack()

                    # Store frame reference and bind click with highlight
                    self.theme_frames[path] = img_frame
                    label.bind("<Button-1>", lambda e, p=path, f=img_frame: self.on_theme_click_with_highlight(p, f))

                    # Bind mouse enter to labels too
                    label.bind("<Enter>", on_mouse_enter)
                    img_frame.bind("<Enter>", on_mouse_enter)

                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1
                except Exception as e:
                    print(f"Error loading {path}: {e}")

        # Update scroll region and canvas window width after all items are added
        frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        # Make the frame width match required width for 5 columns
        frame_width = max_cols * (img_size[0] + 20)
        
        # Bind to configure event to keep frame width fixed
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=frame_width)

        canvas.bind("<Configure>", on_canvas_configure)


    def on_theme_click_with_highlight(self, theme_path, frame):
        """Handle theme click with visual highlighting"""
        # Unhighlight previous selection
        if self.selected_theme_frame:
            self.selected_theme_frame.configure(bg="#444444", padx=2, pady=2)
        
        # Highlight new selection
        frame.configure(bg="#4CAF50", padx=3, pady=3)
        self.selected_theme_frame = frame

        if self.selected_video_frame:
            self.selected_video_frame.configure(bg="#444444", padx=2, pady=2)

        # Call original handler
        self.on_theme_click(theme_path)


    def on_video_click_with_highlight(self, video_preview_path, frame):
        """Handle video click with visual highlighting"""
        # Unhighlight previous selection
        if self.selected_video_frame:
            self.selected_video_frame.configure(bg="#444444", padx=2, pady=2)

        # Highlight new selection
        frame.configure(bg="#9C27B0", padx=3, pady=3)
        self.selected_video_frame = frame
        
        # Call original handler
        self.on_video_click(video_preview_path)


    def on_theme_click(self, theme_path):
        theme_dir = os.path.dirname(theme_path)
        config_path = os.path.join(theme_dir, "lcd_config.json")
        image_path = os.path.join(theme_dir, "01.png")
        if os.path.exists(config_path):
            self.config_manager.load_config(config_path)
        self.config_manager.update_config_value("image_background_path", image_path)
        if callable(self.apply_theme_callback):
            self.apply_theme_callback(image_path)


    def on_video_click(self, video_preview_path):
        video_name = os.path.splitext(os.path.basename(video_preview_path))[0]
        for ext in (".mp4", ".avi", ".mov", ".mkv"):
            video_path = os.path.join(os.path.dirname(video_preview_path), video_name + ext)
            if os.path.exists(video_path):
                self.config_manager.update_config_value("video_background_path", video_path)
                if callable(self.apply_video_callback):
                    self.apply_video_callback(video_path)
                break


    def save_config(self):
        config_file = self.config_wrapper.get_config_file(self.configfile)
        self.config = self.config_wrapper.get_config()
        self.config_wrapper.save_config(self.config, config_file)


    def reset_defaults(self):
        """Call the main GUI's reset function"""
        if callable(self.reset_config_callback):
            self.reset_config_callback()
