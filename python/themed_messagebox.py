"""
Themed messagebox module to match the dark theme of the TR Driver application.
Drop-in replacement for tkinter.messagebox with matching aesthetics.
"""

import tkinter as tk
from tkinter import font as tkfont


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
