import customtkinter as ctk
from pathlib import Path
from typing import Callable, Dict, Optional
from utils.logger import Logger
from utils.exceptions import JustDownloadItError
from downloader.youtube_downloader import YouTubeDownloader

logger = Logger.get_logger(__name__)

class SettingsPanel(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_folder_change: Optional[Callable[[Path], None]] = None,
        on_threads_change: Optional[Callable[[int], None]] = None,
        on_format_change: Optional[Callable[[], None]] = None,
        on_max_downloads_change: Optional[Callable[[int], None]] = None,
        **kwargs
    ):
        try:
            logger.info("Initializing settings panel")
            super().__init__(master, **kwargs)
            
            self.on_folder_change = on_folder_change
            self.on_threads_change = on_threads_change
            self.on_format_change = on_format_change
            self.on_max_downloads_change = on_max_downloads_change
            
            # Download folder selection
            logger.debug("Creating folder selection")
            folder_frame = ctk.CTkFrame(self)
            folder_frame.pack(fill="x", padx=10, pady=5)
            
            # Create a frame for the label and entry (left side)
            left_frame = ctk.CTkFrame(folder_frame, fg_color="transparent")
            left_frame.pack(side="left", fill="x", expand=True, padx=5)
            
            ctk.CTkLabel(left_frame, text="Download Folder:").pack(
                side="left", padx=5
            )
            
            # Use project's downloads folder as default
            default_path = Path(__file__).parent.parent / "downloads"
            self.folder_var = ctk.StringVar(value=str(default_path))
            folder_entry = ctk.CTkEntry(
                left_frame,
                textvariable=self.folder_var
            )
            folder_entry.pack(side="left", fill="x", expand=True, padx=5)
            
            # Create a frame for the buttons (right side)
            button_frame = ctk.CTkFrame(folder_frame, fg_color="transparent")
            button_frame.pack(side="right", padx=5)
            
            browse_btn = ctk.CTkButton(
                button_frame,
                text="Browse",
                width=70,
                command=self._browse_folder
            )
            browse_btn.pack(side="left", padx=2)
            # Add Open button next to Browse
            open_folder_btn = ctk.CTkButton(
                button_frame,
                text="Open",
                width=70,
                command=self._open_download_folder
            )
            open_folder_btn.pack(side="left", padx=2)
            logger.debug(f"Initial download folder: {self.folder_var.get()}")
            
            # Max concurrent downloads selection
            logger.debug("Creating max concurrent downloads selection")
            max_downloads_frame = ctk.CTkFrame(self)
            max_downloads_frame.pack(fill="x", padx=10, pady=5)
            
            ctk.CTkLabel(max_downloads_frame, text="Max. Concurrent Downloads:").pack(
                side="left", padx=5
            )
            
            self.max_downloads_var = ctk.StringVar(value="4")
            max_downloads_entry = ctk.CTkEntry(
                max_downloads_frame,
                textvariable=self.max_downloads_var,
                width=50,
                justify="center"
            )
            max_downloads_entry.pack(side="left", padx=5)
            max_downloads_entry.bind('<FocusOut>', self._validate_max_downloads)
            max_downloads_entry.bind('<Return>', self._validate_max_downloads)
            logger.debug(f"Initial max concurrent downloads: {self.max_downloads_var.get()}")
            
            # Thread count selection
            logger.debug("Creating thread count selection")
            thread_frame = ctk.CTkFrame(self)
            thread_frame.pack(fill="x", padx=10, pady=5)
            
            # Create a frame for the label (left side)
            thread_label_frame = ctk.CTkFrame(thread_frame, fg_color="transparent")
            thread_label_frame.pack(side="left", padx=5)
            
            ctk.CTkLabel(thread_label_frame, text="Download Threads (Regular Downloads):").pack(
                side="left"
            )
            
            # Create a frame for the slider and count (right side)
            thread_control_frame = ctk.CTkFrame(thread_frame, fg_color="transparent")
            thread_control_frame.pack(side="right", padx=5)
            
            self.thread_var = ctk.IntVar(value=4)
            thread_slider = ctk.CTkSlider(
                thread_control_frame,
                from_=1,
                to=20,
                number_of_steps=19,
                variable=self.thread_var,
                command=self._on_thread_change
            )
            thread_slider.pack(side="left", padx=5)
            
            thread_label = ctk.CTkLabel(thread_control_frame, textvariable=self.thread_var)
            thread_label.pack(side="left", padx=5)
            logger.debug(f"Initial thread count: {self.thread_var.get()}")
            
            # YouTube format selection
            logger.debug("Creating YouTube format selection")
            self.format_frame = ctk.CTkFrame(self)
            # Initially hidden, will be shown when URLs are added
            # self.format_frame.pack(fill="x", padx=10, pady=5)
            
            # Create inner frame to maintain order of elements
            self.inner_frame = ctk.CTkFrame(self.format_frame, fg_color="transparent")
            self.inner_frame.pack(fill="x", padx=0, pady=0)
            
            # Create horizontal frame for checkboxes
            self.checkbox_frame = ctk.CTkFrame(self.inner_frame, fg_color="transparent")
            self.checkbox_frame.pack(fill="x", padx=0, pady=0)
            
            # Audio toggle
            self.audio_enabled = ctk.BooleanVar(value=False)
            self.audio_check = ctk.CTkCheckBox(
                self.checkbox_frame,
                text="Audio",
                variable=self.audio_enabled,
                command=self._on_audio_toggle
            )
            self.audio_check.pack(side="left", padx=5, pady=2)
            logger.debug(f"Initial audio enabled: {self.audio_enabled.get()}")
            
            # Video toggle
            self.video_enabled = ctk.BooleanVar(value=False)
            self.video_check = ctk.CTkCheckBox(
                self.checkbox_frame,
                text="Video",
                variable=self.video_enabled,
                command=self._on_video_toggle
            )
            self.video_check.pack(side="left", padx=5, pady=2)
            logger.debug(f"Initial video enabled: {self.video_enabled.get()}")
            
            # Initially hide both checkboxes since no URLs are present
            self.audio_check.pack_forget()
            self.video_check.pack_forget()
            
            # Initially hide the checkbox frame since no checkboxes are visible
            self.checkbox_frame.pack_forget()
            
            # Muxing toggle (only visible when both audio and video are checked)
            self.muxing_enabled = ctk.BooleanVar(value=False)
            self.muxing_check = ctk.CTkCheckBox(
                self.checkbox_frame,
                text="Muxing",
                variable=self.muxing_enabled,
                command=self._on_muxing_toggle
            )
            # Initially hidden, will be shown when both audio and video are checked
            logger.debug(f"Initial muxing enabled: {self.muxing_enabled.get()}")
            
            # Create horizontal frame for quality settings
            self.quality_settings_frame = ctk.CTkFrame(self.inner_frame, fg_color="transparent")
            # Initially not packed, will be packed when audio or video is enabled
            
            # Audio quality frame
            self.audio_frame = ctk.CTkFrame(self.quality_settings_frame)
            # Initially hidden, will be shown when audio is checked
            
            ctk.CTkLabel(self.audio_frame, text="Audio Quality:").pack(
                side="left", padx=5
            )
            
            # Get audio quality options from YouTubeDownloader
            audio_qualities = list(YouTubeDownloader.AUDIO_FORMATS.keys())
            self.audio_quality = ctk.StringVar(value="High (m4a)")
            audio_menu = ctk.CTkOptionMenu(
                self.audio_frame,
                values=audio_qualities,
                variable=self.audio_quality,
                command=self._on_format_change
            )
            audio_menu.pack(side="left", padx=5)
            logger.debug(f"Initial audio quality: {self.audio_quality.get()}")
            
            # Video quality frame
            self.quality_frame = ctk.CTkFrame(self.quality_settings_frame)
            # Initially hidden, will be shown when video is checked
            
            ctk.CTkLabel(self.quality_frame, text="Video Quality:").pack(
                side="left", padx=5
            )
            
            # Get video quality options from YouTubeDownloader
            video_qualities = list(YouTubeDownloader.VIDEO_FORMATS.keys())
            self.video_quality = ctk.StringVar(value="1080p")
            self.quality_menu = ctk.CTkOptionMenu(
                self.quality_frame,
                values=video_qualities,
                variable=self.video_quality,
                command=self._on_format_change
            )
            self.quality_menu.pack(side="left", padx=5)
            logger.debug(f"Initial video quality: {self.video_quality.get()}")
            
            logger.info("Settings panel initialization complete")
        except Exception as e:
            logger.error(f"Error initializing settings panel: {str(e)}", exc_info=True)
            raise JustDownloadItError(f"Error initializing settings panel: {str(e)}")
        
    def _on_audio_toggle(self):
        """Handle audio toggle"""
        is_audio_enabled = self.audio_enabled.get()
        logger.debug(f"Audio toggled: {is_audio_enabled}")
        
        if is_audio_enabled:
            # Pack quality settings frame if not already packed
            try:
                self.quality_settings_frame.pack_info()
            except:
                self.quality_settings_frame.pack(fill="x", padx=0, pady=0)
            # Show audio quality frame
            self.audio_frame.pack(side="left", padx=5, pady=2)
        else:
            # Hide audio quality frame
            self.audio_frame.pack_forget()
            # Uncheck muxing if audio is unchecked
            self.muxing_enabled.set(False)
            # Hide quality settings frame if no audio or video is enabled
            self._update_quality_settings_visibility()
        
        # Update muxing checkbox visibility
        self._update_muxing_visibility()
        
        if self.on_format_change:
            self.on_format_change()
            
    def _on_video_toggle(self):
        """Handle video toggle"""
        is_video_enabled = self.video_enabled.get()
        logger.debug(f"Video toggled: {is_video_enabled}")
        
        if is_video_enabled:
            # Pack quality settings frame if not already packed
            try:
                self.quality_settings_frame.pack_info()
            except:
                self.quality_settings_frame.pack(fill="x", padx=0, pady=0)
            # Show video quality frame
            self.quality_frame.pack(side="left", padx=5, pady=2)
        else:
            # Hide video quality frame
            self.quality_frame.pack_forget()
            # Uncheck muxing if video is unchecked
            self.muxing_enabled.set(False)
            # Hide quality settings frame if no audio or video is enabled
            self._update_quality_settings_visibility()
        
        # Update muxing checkbox visibility
        self._update_muxing_visibility()
        
        if self.on_format_change:
            self.on_format_change()
    
    def _on_muxing_toggle(self):
        """Handle muxing toggle"""
        is_muxing_enabled = self.muxing_enabled.get()
        logger.debug(f"Muxing toggled: {is_muxing_enabled}")
        
        if self.on_format_change:
            self.on_format_change()
    
    def _update_muxing_visibility(self):
        """Update muxing checkbox visibility based on audio and video states"""
        audio_enabled = self.audio_enabled.get()
        video_enabled = self.video_enabled.get()
        
        if audio_enabled and video_enabled:
            # Show muxing checkbox when both audio and video are enabled
            self.muxing_check.pack(side="left", padx=5, pady=2)
        else:
            # Hide muxing checkbox and uncheck it
            self.muxing_check.pack_forget()
            self.muxing_enabled.set(False)
            
    def _update_quality_settings_visibility(self):
        """Update quality settings frame visibility based on audio and video states"""
        audio_enabled = self.audio_enabled.get()
        video_enabled = self.video_enabled.get()
        
        if not audio_enabled and not video_enabled:
            # Hide quality settings frame when neither audio nor video is enabled
            try:
                self.quality_settings_frame.pack_forget()
            except:
                pass  # Frame might not be packed yet
                
    def _detect_url_formats(self, urls: list) -> tuple[bool, bool]:
        """Detect if URLs contain audio or video formats"""
        audio_formats = ['.mp3', '.m4a', '.wav', '.flac', '.aac', '.ogg', '.wma']
        video_formats = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
        
        has_audio_urls = False
        has_video_urls = False
        
        for url in urls:
            url_lower = url.lower()
            
            # Check for YouTube URLs (can contain both audio and video)
            if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
                has_audio_urls = True
                has_video_urls = True
                continue
                
            # Check for audio formats
            if any(format_ext in url_lower for format_ext in audio_formats):
                has_audio_urls = True
                
            # Check for video formats
            if any(format_ext in url_lower for format_ext in video_formats):
                has_video_urls = True
                
        return has_audio_urls, has_video_urls
        
    def update_checkbox_visibility(self, urls: list):
        """Update checkbox visibility based on URL content"""
        has_audio_urls, has_video_urls = self._detect_url_formats(urls)
        
        # Show/hide audio checkbox
        if has_audio_urls:
            self.audio_check.pack(side="left", padx=5, pady=2)
        else:
            self.audio_check.pack_forget()
            # Uncheck audio if hidden
            self.audio_enabled.set(False)
            
        # Show/hide video checkbox
        if has_video_urls:
            self.video_check.pack(side="left", padx=5, pady=2)
        else:
            self.video_check.pack_forget()
            # Uncheck video if hidden
            self.video_enabled.set(False)
            
        # Show/hide checkbox frame based on whether any checkboxes are visible
        if has_audio_urls or has_video_urls:
            try:
                self.checkbox_frame.pack_info()
            except:
                self.checkbox_frame.pack(fill="x", padx=0, pady=0)
            # Show format frame when checkboxes are visible
            try:
                self.format_frame.pack_info()
            except:
                self.format_frame.pack(fill="x", padx=10, pady=5)
        else:
            self.checkbox_frame.pack_forget()
            # Hide format frame when no checkboxes are visible
            self.format_frame.pack_forget()
            
        # Update muxing visibility
        self._update_muxing_visibility()
        
        # Update quality settings visibility
        self._update_quality_settings_visibility()
            
    def _browse_folder(self):
        """Open folder selection dialog"""
        logger.debug("Opening folder selection dialog")
        folder = ctk.filedialog.askdirectory(
            initialdir=self.folder_var.get()
        )
        if folder:
            logger.info(f"Selected download folder: {folder}")
            self.folder_var.set(folder)
            if self.on_folder_change:
                self.on_folder_change(Path(folder))
                
    def _open_download_folder(self):
        """Open the selected download folder in the OS file explorer"""
        import os
        import subprocess
        folder = self.folder_var.get()
        if os.path.exists(folder):
            try:
                if os.name == 'nt':
                    os.startfile(folder)
                elif os.name == 'posix':
                    subprocess.Popen(['xdg-open', folder])
                else:
                    subprocess.Popen(['open', folder])
            except Exception as e:
                logger.error(f"Failed to open folder: {str(e)}", exc_info=True)
        else:
            logger.debug("Open folder button clicked but folder does not exist.")
            
    def _on_thread_change(self, value):
        """Handle thread count change"""
        threads = int(float(value))  # Convert from float to int
        logger.debug(f"Thread count changed to {threads}")
        if self.on_threads_change:
            self.on_threads_change(threads)
            
    def _on_format_change(self, *args):
        """Handle format change"""
        logger.debug(
            f"Format changed - Video: {self.video_quality.get()}, "
            f"Audio: {self.audio_quality.get()}, "
            f"Audio Enabled: {self.audio_enabled.get()}, "
            f"Video Enabled: {self.video_enabled.get()}, "
            f"Muxing Enabled: {self.muxing_enabled.get()}"
        )
        if self.on_format_change:
            self.on_format_change()
            
    def _validate_max_downloads(self, event=None):
        """Validate and update max downloads value"""
        try:
            value = int(self.max_downloads_var.get())
            if value < 1:
                value = 1
            elif value > 100:
                value = 100
            self.max_downloads_var.set(str(value))
            if self.on_max_downloads_change:
                self.on_max_downloads_change(value)
        except ValueError:
            # Reset to default if invalid input
            self.max_downloads_var.set("4")
            if self.on_max_downloads_change:
                self.on_max_downloads_change(4)
        logger.debug(f"Max concurrent downloads updated to: {self.max_downloads_var.get()}")

    def get_settings(self) -> Dict:
        """Get current settings"""
        settings = {
            'download_folder': Path(self.folder_var.get()),
            'video_quality': self.video_quality.get(),
            'audio_quality': self.audio_quality.get(),
            'audio_enabled': self.audio_enabled.get(),
            'video_enabled': self.video_enabled.get(),
            'muxing_enabled': self.muxing_enabled.get()
        }
        logger.debug(f"Current settings: {settings}")
        return settings

    def get_max_downloads(self) -> int:
        """Get current max downloads setting"""
        try:
            return int(self.max_downloads_var.get())
        except ValueError:
            return 4
