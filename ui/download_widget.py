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
        file_type: str = "file",  # new parameter: 'file', 'audio', 'video', 'muxing'
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
        title_row = ctk.CTkFrame(content)
        title_row.pack(fill="x", padx=0, pady=(2,0))
        self.title_label = ctk.CTkLabel(
            title_row,
            text=title,
            anchor="w",
            font=("", 12, "bold")
        )
        self.title_label.pack(side="left", fill="x", expand=True, padx=5)
        # Add [X] close button
        self.close_btn = ctk.CTkButton(
            title_row,
            text="✕",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color="#b22222",
            text_color="#b22222",
            font=("", 12, "bold"),
            command=self._on_close_click
        )
        self.close_btn.pack(side="right", padx=2)
        
        # Progress section
        self.progress_frame = ctk.CTkFrame(content)
        self.progress_frame.pack(fill="x", pady=(2,0))

        # File progress (generic)
        self.file_frame = ctk.CTkFrame(self.progress_frame)
        self.file_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(self.file_frame, text="File:", width=50).pack(side="left", padx=5)
        self.file_progress = ctk.CTkProgressBar(self.file_frame)
        self.file_progress.pack(side="left", fill="x", expand=True, padx=5)
        self.file_progress.set(0)
        self.file_label = ctk.CTkLabel(self.file_frame, text="", width=150)
        self.file_label.pack(side="left", padx=5)

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

        # Hide all progress bars initially
        self.file_frame.pack_forget()
        self.video_frame.pack_forget()
        self.audio_frame.pack_forget()
        self.muxing_frame.pack_forget()

        # Show the correct progress bar based on file_type
        if file_type == "file":
            self.file_frame.pack(fill="x", pady=2)
        elif file_type == "audio":
            self.audio_frame.pack(fill="x", pady=2)
        elif file_type == "video":
            self.video_frame.pack(fill="x", pady=2)
        elif file_type == "muxing":
            self.muxing_frame.pack(fill="x", pady=2)

        # Status and open
        status_frame = ctk.CTkFrame(content)
        status_frame.pack(fill="x", pady=(2,2))
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Preparing download...",
            anchor="w"
        )
        self.status_label.pack(side="left", padx=5)
        # Repurpose Clear button to Open
        self.open_btn = ctk.CTkButton(
            status_frame,
            text="Open",
            width=60,
            command=self._on_open_click
        )
        self.open_btn.pack(side="right", padx=5)
        self.open_btn.configure(state="disabled")  # Initially disabled
        logger.debug(f"Download widget created with URL: {self.url} and file_type: {file_type}")
        
        # Debug: Check what parameters are available on progress bars
        try:
            logger.debug(f"Progress bar config keys: {list(self.file_progress.configure().keys())}")
        except Exception as e:
            logger.debug(f"Could not get progress bar config: {e}")
        
    def _set_progress_color(self, progress_bar, color: str):
        """Set the color of a progress bar"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                # Try different possible parameter names for CustomTkinter progress bars
                try:
                    progress_bar.configure(progress_color=color)
                    logger.debug(f"Set progress bar color to: {color} using progress_color")
                except:
                    try:
                        progress_bar.configure(fg_color=color)
                        logger.debug(f"Set progress bar color to: {color} using fg_color")
                    except:
                        progress_bar.configure(progress_color=color)
                        logger.debug(f"Set progress bar color to: {color} using progress_color (fallback)")
            except Exception as e:
                logger.error(f"Error setting progress color: {str(e)}", exc_info=True)
                
    def _set_all_progress_colors(self, color: str):
        """Set all visible progress bars to the same color"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                # Check which progress bars are visible and set their colors
                if self.file_frame.winfo_viewable():
                    self._set_progress_color(self.file_progress, color)
                if self.video_frame.winfo_viewable():
                    self._set_progress_color(self.video_progress, color)
                if self.audio_frame.winfo_viewable():
                    self._set_progress_color(self.audio_progress, color)
                if self.muxing_frame.winfo_viewable():
                    self._set_progress_color(self.muxing_progress, color)
            except Exception as e:
                logger.error(f"Error setting all progress colors: {str(e)}", exc_info=True)
        
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
            
    def show_file_progress(self):
        if not self.is_destroyed:
            self.file_frame.pack(fill="x", pady=2)
            
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
            
    def update_file_progress(self, progress: float, speed: str = "", downloaded: str = "", total: str = ""):
        if not self.is_destroyed and self.winfo_exists():
            try:
                self.file_progress.set(min(1.0, progress / 100))
                if speed and downloaded and total:
                    self.file_label.configure(text=f"{downloaded}/{total} ({speed})")
            except Exception as e:
                logger.error(f"Error updating file progress: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error updating file progress: {str(e)}")
            
    def update_title(self, title: str):
        """Update the widget's title"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                self.title_label.configure(text=title)
            except Exception as e:
                logger.error(f"Error updating title: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error updating title: {str(e)}")
            
    def set_status(self, status: str):
        """Update status text and enable Open button if download is complete"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                self.status_label.configure(text=status)
                logger.debug(f"Setting status to: '{status}'")
                
                # Set progress bar colors based on status
                status_lower = status.lower()
                if status_lower.startswith("error:"):
                    self.is_cancelled = True
                    self.open_btn.configure(text="Open", state="disabled")
                    # Keep default color for errors
                    logger.debug("Status indicates error - keeping default color")
                elif "muxing" in status_lower or "preparing" in status_lower or "fetching" in status_lower or status_lower.startswith("starting download"):
                    # Yellow for muxing, preparing, fetching information, or starting download
                    logger.debug("Status indicates muxing/preparing/fetching/starting - setting yellow")
                    self._set_all_progress_colors("#FFD700")  # Gold/yellow
                elif status_lower.startswith("download complete") or status_lower.startswith("finished") or status_lower.startswith("finished!"):
                    # Green for completed downloads
                    logger.debug("Status indicates completion - setting green")
                    self._set_all_progress_colors("#32CD32")  # Lime green
                    self.open_btn.configure(state="normal")
                elif status_lower.startswith("download cancelled") or status_lower.startswith("download failed"):
                    self.open_btn.configure(text="Open", state="disabled")
                    # Keep default color for cancelled/failed
                    logger.debug("Status indicates cancelled/failed - keeping default color")
                else:
                    # Default color for other statuses (downloading, etc.)
                    logger.debug("Status indicates downloading - setting blue")
                    self._set_all_progress_colors("#1f538d")  # Default blue
                    self.open_btn.configure(state="disabled")
            except Exception as e:
                logger.error(f"Error setting status: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error setting status: {str(e)}")
    
    def set_downloaded_path(self, file_path):
        """Set the path(s) of the downloaded file(s)"""
        if not self.is_destroyed and self.winfo_exists():
            try:
                if isinstance(file_path, list):
                    self.downloaded_paths = file_path
                else:
                    self.downloaded_paths = [file_path]
                logger.debug(f"Set downloaded path(s) for widget {self.id}: {self.downloaded_paths}")
            except Exception as e:
                logger.error(f"Error setting downloaded path: {str(e)}", exc_info=True)
                raise JustDownloadItError(f"Error setting downloaded path: {str(e)}")
            
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
                    # self.cancel_btn.configure(text="Clear") # Removed as per edit hint
                else:
                    # Clear the widget
                    if self.on_clear:
                        self.on_clear()
                    self.destroy()
            except Exception:
                pass  # Ignore errors if widget is being destroyed
                
    def _on_open_click(self):
        """Open the downloaded file(s) if available"""
        import os
        import subprocess
        if hasattr(self, 'downloaded_paths') and self.downloaded_paths:
            for path in self.downloaded_paths:
                if path and os.path.exists(path):
                    try:
                        if os.name == 'nt':
                            os.startfile(path)
                        elif os.name == 'posix':
                            subprocess.Popen(['xdg-open', path])
                        else:
                            subprocess.Popen(['open', path])
                    except Exception as e:
                        logger.error(f"Failed to open file: {str(e)}", exc_info=True)
        else:
            logger.debug("Open button clicked but file(s) do not exist or are not ready.")
                
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
            # self.cancel_btn.configure(text="Clear") # Removed as per edit hint
            if self.on_cancel:
                self.on_cancel(self.id)

    def _on_close_click(self):
        """Handle close button: cancel if in progress, clear if finished/cancelled"""
        if not self.is_completed and not self.is_cancelled:
            if self.on_cancel:
                self.on_cancel(self.id)
        else:
            self.destroy()
