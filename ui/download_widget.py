import customtkinter as ctk
import tkinter as tk  # Import tkinter for Canvas
import uuid
from typing import Callable, Optional
from utils.logger import Logger
from utils.exceptions import JustDownloadItError

logger = Logger.get_logger(__name__)

class DownloadWidget(ctk.CTkFrame):
    def __init__(
        self,
        master,
        url: str,
        title: str,
        on_cancel: Optional[Callable[[], None]] = None,
        on_clear: Optional[Callable[[], None]] = None,
        **kwargs
    ):
        """Initialize download widget"""
        super().__init__(master, **kwargs)
        
        self.url = url
        self.id = str(uuid.uuid4())  # Generate unique ID for this widget
        self.process_id = None  # Store process ID for cancellation
        self.is_cancelled = False
        self.is_completed = False  # Initialize is_completed attribute
        self.on_cancel = on_cancel
        self.on_clear = on_clear
        self.is_destroyed = False  # Track if widget is destroyed
        
        # Create main content frame
        content = ctk.CTkFrame(self)
        content.pack(fill="x", padx=5, pady=2)
        
        # Title
        self.title_label = ctk.CTkLabel(
            content,
            text=title,
            anchor="w",
            font=("", 12, "bold")
        )
        self.title_label.pack(fill="x", padx=5, pady=(2,0))
        
        # Progress section
        self.progress_frame = ctk.CTkFrame(content)
        self.progress_frame.pack(fill="x", pady=(2,0))
        
        # Video progress
        self.video_frame = ctk.CTkFrame(self.progress_frame)
        self.video_frame.pack(fill="x", pady=2)
        
        ctk.CTkLabel(self.video_frame, text="Video:", width=50).pack(side="left", padx=5)
        
        self.video_progress = ctk.CTkProgressBar(self.video_frame)
        self.video_progress.pack(side="left", fill="x", expand=True, padx=5)
        self.video_progress.set(0)
        
        self.video_label = ctk.CTkLabel(self.video_frame, text="", width=150)
        self.video_label.pack(side="left", padx=5)
        
        # Audio progress
        self.audio_frame = ctk.CTkFrame(self.progress_frame)
        self.audio_frame.pack(fill="x", pady=2)
        
        ctk.CTkLabel(self.audio_frame, text="Audio:", width=50).pack(side="left", padx=5)
        
        self.audio_progress = ctk.CTkProgressBar(self.audio_frame)
        self.audio_progress.pack(side="left", fill="x", expand=True, padx=5)
        self.audio_progress.set(0)
        
        self.audio_label = ctk.CTkLabel(self.audio_frame, text="", width=150)
        self.audio_label.pack(side="left", padx=5)
        
        # Muxing progress
        self.muxing_frame = ctk.CTkFrame(self.progress_frame)
        self.muxing_frame.pack(fill="x", pady=2)  # Pack initially so it's properly configured
        
        ctk.CTkLabel(self.muxing_frame, text="Muxing:", width=50).pack(side="left", padx=5)
        
        self.muxing_progress = ctk.CTkProgressBar(self.muxing_frame)
        self.muxing_progress.pack(side="left", fill="x", expand=True, padx=5)
        self.muxing_progress.set(0)
        
        self.muxing_label = ctk.CTkLabel(self.muxing_frame, text="", width=150)
        self.muxing_label.pack(side="left", padx=5)
        
        # Hide progress bars initially
        self.video_frame.pack_forget()
        self.audio_frame.pack_forget()
        self.muxing_frame.pack_forget()
        
        # Status and cancel
        status_frame = ctk.CTkFrame(content)
        status_frame.pack(fill="x", pady=(2,2))
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Preparing download...",
            anchor="w"
        )
        self.status_label.pack(side="left", padx=5)
        
        self.cancel_btn = ctk.CTkButton(
            status_frame,
            text="Cancel",
            width=60,
            command=self._on_button_click
        )
        self.cancel_btn.pack(side="right", padx=5)
        
        logger.debug(f"Download widget created with URL: {self.url}")
        
    def show_video_progress(self):
        """Show video progress bar"""
        if not self.is_destroyed:
            self.video_frame.pack(fill="x", pady=2)
            
    def show_audio_progress(self):
        """Show audio progress bar"""
        if not self.is_destroyed:
            self.audio_frame.pack(fill="x", pady=2)
            
    def show_muxing_progress(self):
        """Show muxing progress bar and hide video/audio progress"""
        if not self.is_destroyed:
            # Hide video and audio frames
            self.video_frame.pack_forget()
            self.audio_frame.pack_forget()
            
            # Show muxing frame within the progress frame
            self.muxing_frame.pack(fill="x", pady=2)
            self.progress_frame.update()  # Force update to ensure proper layout
            
    def update_video_progress(self, progress: float, speed: str = "", downloaded: str = "", total: str = ""):
        """Update video download progress"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                # Progress is already a percentage (0-100), convert to 0-1 for progress bar
                self.video_progress.set(min(1.0, progress / 100))
                if speed and downloaded and total:
                    self.video_label.configure(text=f"{downloaded}/{total} ({speed})")
            except Exception as e:
                logger.error(f"Error updating video progress: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error updating video progress: {str(e)}")
            
    def update_audio_progress(self, progress: float, speed: str = "", downloaded: str = "", total: str = ""):
        """Update audio download progress"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                # Progress is already a percentage (0-100), convert to 0-1 for progress bar
                self.audio_progress.set(min(1.0, progress / 100))
                if speed and downloaded and total:
                    self.audio_label.configure(text=f"{downloaded}/{total} ({speed})")
            except Exception as e:
                logger.error(f"Error updating audio progress: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error updating audio progress: {str(e)}")
            
    def update_muxing_progress(self, progress: float, status: str = ""):
        """Update muxing progress"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                # Progress is already a percentage (0-100), convert to 0-1 for progress bar
                self.muxing_progress.set(min(1.0, progress / 100))
                if status:
                    self.muxing_label.configure(text=status)
            except Exception as e:
                logger.error(f"Error updating muxing progress: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error updating muxing progress: {str(e)}")
            
    def update_title(self, title: str):
        """Update the widget's title"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                self.title_label.configure(text=title)
            except Exception as e:
                logger.error(f"Error updating title: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error updating title: {str(e)}")
            
    def set_status(self, status: str):
        """Update status text"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                self.status_label.configure(text=status)
                if status.startswith("Error:"):
                    self.is_cancelled = True
                    self.cancel_btn.configure(text="Clear")
            except Exception as e:
                logger.error(f"Error setting status: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error setting status: {str(e)}")
            
    def hide_progress_frame(self):
        """Hide the entire progress section"""
        if not self.is_destroyed and self.winfo_exists():
            self.video_frame.pack_forget()
            self.audio_frame.pack_forget()
            self.muxing_frame.pack_forget()
            self.progress_frame.pack_forget()
            
    def _on_button_click(self):
        """Handle button click based on current state"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                if not self.is_cancelled:
                    # Cancel the download
                    if self.on_cancel:
                        self.on_cancel()
                    self.is_cancelled = True
                    self.cancel_btn.configure(text="Clear")
                else:
                    # Clear the widget
                    if self.on_clear:
                        self.on_clear()
                    self.destroy()
            except Exception:
                pass  # Ignore errors if widget is being destroyed
                
    def destroy(self):
        """Override destroy to mark widget as destroyed"""
        self.is_destroyed = True
        super().destroy()

    def _on_cancel(self):
        """Handle cancel button click"""
        if self.is_cancelled or self.is_completed:
            # If already cancelled or completed, clear the widget
            if self.on_cancel:
                self.on_cancel(self.id)
        else:
            # Cancel the download
            self.is_cancelled = True
            self.cancel_btn.configure(text="Clear")
            if self.on_cancel:
                self.on_cancel(self.id)
