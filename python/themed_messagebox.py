"""
Themed messagebox module to match the dark theme of the TR Driver application.
Drop-in replacement for tkinter.messagebox with matching aesthetics.
"""

import tkinter as tk
from tkinter import font as tkfont
import os
from PIL import Image, ImageTk

class ThemedMessageBox(tk.Toplevel):
    """Dark-themed message box matching TR Driver style"""
    
    # Icon colors and symbols
    ICONS = {
        "error": {"symbol": "✗", "color": "#f44336", "bg": "#2b2b2b"},
        "warning": {"symbol": "⚠", "color": "#ff9800", "bg": "#2b2b2b"},
        "info": {"symbol": "ℹ", "color": "#2196F3", "bg": "#2b2b2b"},
        "question": {"symbol": "?", "color": "#4CAF50", "bg": "#2b2b2b"},
    }
    
    def __init__(self, parent, title, message, icon_type="info", buttons=None):
        """
        Create a themed message box.
        
        Args:
            parent: Parent window
            title: Dialog title
            message: Message text
            icon_type: One of "error", "warning", "info", "question"
            buttons: List of button configs [("text", return_value), ...]
                    If None, defaults to single OK button
        """
        super().__init__(parent)
        
        self.result = None
        self.title(title)
        self.configure(bg="#2b2b2b")
        self.resizable(False, False)
        
        # Make modal
        self.transient(parent)
        
        # Get icon config
        icon_config = self.ICONS.get(icon_type, self.ICONS["info"])
        
        # Default buttons
        if buttons is None:
            buttons = [("OK", True)]
        
        self._setup_ui(message, icon_config, buttons)
        self._center_on_parent(parent)
        
        # Grab focus after window is ready
        self.update_idletasks()
        try:
            self.grab_set()
        except:
            pass
        
        # Focus first button
        if hasattr(self, '_buttons') and self._buttons:
            self._buttons[0].focus_set()
    
    def _setup_ui(self, message, icon_config, buttons):
        """Setup the UI components"""
        # Main container
        main_frame = tk.Frame(self, bg="#2b2b2b")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Content frame (icon + message)
        content_frame = tk.Frame(main_frame, bg="#2b2b2b")
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Icon
        icon_label = tk.Label(
            content_frame,
            text=icon_config["symbol"],
            font=("Arial", 48, "bold"),
            fg=icon_config["color"],
            bg="#2b2b2b"
        )
        icon_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # Message
        message_label = tk.Label(
            content_frame,
            text=message,
            font=("Arial", 11),
            fg="#FFFFFF",
            bg="#2b2b2b",
            justify=tk.LEFT,
            wraplength=400
        )
        message_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Button frame
        button_frame = tk.Frame(main_frame, bg="#2b2b2b")
        button_frame.pack(fill=tk.X)
        
        # Create buttons
        self._buttons = []
        for i, (text, return_value) in enumerate(buttons):
            # Color scheme based on button type
            if text.lower() in ["ok", "yes"]:
                bg_color = "#4CAF50"
                hover_color = "#45A049"
            elif text.lower() in ["cancel", "no"]:
                bg_color = "#f44336"
                hover_color = "#da190b"
            else:
                bg_color = "#2196F3"
                hover_color = "#0b7dda"
            
            btn = tk.Button(
                button_frame,
                text=text,
                font=("Arial", 10, "bold"),
                bg=bg_color,
                fg="white",
                activebackground=hover_color,
                activeforeground="white",
                relief="flat",
                cursor="hand2",
                padx=20,
                pady=8,
                command=lambda val=return_value: self._on_button_click(val)
            )
            btn.pack(side=tk.RIGHT, padx=(5, 0) if i > 0 else 0)
            self._buttons.append(btn)
            
            # Hover effects
            btn.bind("<Enter>", lambda e, b=btn, c=hover_color: b.config(bg=c))
            btn.bind("<Leave>", lambda e, b=btn, c=bg_color: b.config(bg=c))
        
        # Bind Enter and Escape keys
        self.bind("<Return>", lambda e: self._on_button_click(buttons[0][1]))
        if len(buttons) > 1:
            self.bind("<Escape>", lambda e: self._on_button_click(buttons[-1][1]))
    
    def _on_button_click(self, value):
        """Handle button click"""
        self.result = value
        self.destroy()
    
    def _center_on_parent(self, parent):
        """Center dialog on parent window"""
        self.update_idletasks()
        
        # Get dimensions
        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()
        
        if parent:
            # Center on parent
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()
            
            x = parent_x + (parent_width - dialog_width) // 2
            y = parent_y + (parent_height - dialog_height) // 2
        else:
            # Center on screen
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            
            x = (screen_width - dialog_width) // 2
            y = (screen_height - dialog_height) // 2
        
        self.geometry(f"+{x}+{y}")
    
    def show(self):
        """Show dialog and return result"""
        self.wait_window()
        return self.result


# Convenience functions matching tkinter.messagebox API

def showerror(title, message, parent=None):
    """Show an error message dialog"""
    dialog = ThemedMessageBox(
        parent or tk._default_root,
        title,
        message,
        icon_type="error",
        buttons=[("OK", None)]
    )
    return dialog.show()


def showwarning(title, message, parent=None):
    """Show a warning message dialog"""
    dialog = ThemedMessageBox(
        parent or tk._default_root,
        title,
        message,
        icon_type="warning",
        buttons=[("OK", None)]
    )
    return dialog.show()


def showinfo(title, message, parent=None):
    """Show an info message dialog"""
    dialog = ThemedMessageBox(
        parent or tk._default_root,
        title,
        message,
        icon_type="info",
        buttons=[("OK", None)]
    )
    return dialog.show()


def askquestion(title, message, parent=None):
    """Ask a yes/no question"""
    dialog = ThemedMessageBox(
        parent or tk._default_root,
        title,
        message,
        icon_type="question",
        buttons=[("Yes", "yes"), ("No", "no")]
    )
    result = dialog.show()
    return result if result else "no"


def askyesno(title, message, parent=None):
    """Ask a yes/no question, returns bool"""
    dialog = ThemedMessageBox(
        parent or tk._default_root,
        title,
        message,
        icon_type="question",
        buttons=[("Yes", True), ("No", False)]
    )
    result = dialog.show()
    return result if result is not None else False


def askokcancel(title, message, parent=None):
    """Ask OK/Cancel, returns bool"""
    dialog = ThemedMessageBox(
        parent or tk._default_root,
        title,
        message,
        icon_type="question",
        buttons=[("OK", True), ("Cancel", False)]
    )
    result = dialog.show()
    return result if result is not None else False


def askyesnocancel(title, message, parent=None):
    """Ask Yes/No/Cancel, returns True/False/None"""
    dialog = ThemedMessageBox(
        parent or tk._default_root,
        title,
        message,
        icon_type="question",
        buttons=[("Yes", True), ("No", False), ("Cancel", None)]
    )
    return dialog.show()


def askretrycancel(title, message, parent=None):
    """Ask Retry/Cancel, returns bool"""
    dialog = ThemedMessageBox(
        parent or tk._default_root,
        title,
        message,
        icon_type="warning",
        buttons=[("Retry", True), ("Cancel", False)]
    )
    result = dialog.show()
    return result if result is not None else False


class ThemedAboutBox(tk.Toplevel):
    """Dark-themed About dialog matching TR Driver style"""

    def __init__(self, parent, app_name, version, description, website=None, icon="ℹ", icon_path=None):
        super().__init__(parent)
        self.title(f"About {app_name}")
        self.configure(bg="#2b2b2b")
        self.resizable(False, False)
        self.transient(parent)

        self._setup_ui(app_name, version, description, website, icon, icon_path)
        self._center_on_parent(parent)

        self.update_idletasks()
        try:
            self.grab_set()
        except:
            pass

    def _setup_ui(self, app_name, version, description, website, icon, icon_path):
        main_frame = tk.Frame(self, bg="#2b2b2b")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=25)

        # --- Icon at top ---
        if icon_path and os.path.exists(icon_path):
            try:
                img = Image.open(icon_path).resize((80, 80))
                self._photo = ImageTk.PhotoImage(img)
                icon_label = tk.Label(main_frame, image=self._photo, bg="#2b2b2b")
            except Exception as e:
                print(f"Error loading about icon: {e}")
                icon_label = tk.Label(main_frame, text=icon, font=("Arial", 48, "bold"), fg="#2196F3", bg="#2b2b2b")
        else:
            icon_label = tk.Label(main_frame, text=icon, font=("Arial", 48, "bold"), fg="#2196F3", bg="#2b2b2b")
        icon_label.pack(pady=(0, 10))

        # --- App name & version ---
        title_label = tk.Label(
            main_frame,
            text=f"{app_name}",
            font=("Arial", 16, "bold"),
            fg="#FFFFFF",
            bg="#2b2b2b",
        )
        title_label.pack()

        version_label = tk.Label(
            main_frame,
            text=f"Version {version}",
            font=("Arial", 11),
            fg="#AAAAAA",
            bg="#2b2b2b",
        )
        version_label.pack(pady=(0, 10))

        # --- Separator line ---
        sep = tk.Frame(main_frame, bg="#444444", height=1)
        sep.pack(fill=tk.X, pady=10)

        # --- Description text ---
        desc_label = tk.Label(
            main_frame,
            text=description,
            font=("Arial", 11),
            fg="#CCCCCC",
            bg="#2b2b2b",
            justify=tk.CENTER,
            wraplength=420,
        )
        desc_label.pack(pady=(0, 10))

        # --- Website link ---
        if website:
            site_label = tk.Label(
                main_frame,
                text=website,
                font=("Arial", 10, "underline"),
                fg="#2196F3",
                bg="#2b2b2b",
                cursor="hand2",
            )
            site_label.pack(pady=(0, 10))
            site_label.bind("<Button-1>", lambda e: webbrowser.open(website))

        # --- OK button ---
        ok_button = tk.Button(
            main_frame,
            text="OK",
            font=("Arial", 10, "bold"),
            bg="#4CAF50",
            fg="white",
            activebackground="#45A049",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=20,
            pady=8,
            command=self.destroy,
        )
        ok_button.pack(pady=(10, 0))
        ok_button.focus_set()

    def _center_on_parent(self, parent):
        """Center the dialog on its parent window"""
        self.update_idletasks()
        if parent is not None:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_reqwidth() // 2)
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_reqheight() // 2)
            self.geometry(f"+{x}+{y}")
