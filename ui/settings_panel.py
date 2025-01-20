import customtkinter as ctk
from pathlib import Path
from typing import Callable, Dict, Optional
import logging
from downloader.youtube_downloader import YouTubeDownloader

logger = logging.getLogger(__name__)

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
        
        ctk.CTkLabel(folder_frame, text="Download Folder:").pack(
            side="left", padx=5
        )
        
        # Use project's downloads folder as default
        default_path = Path(__file__).parent.parent / "downloads"
        self.folder_var = ctk.StringVar(value=str(default_path))
        folder_entry = ctk.CTkEntry(
            folder_frame,
            textvariable=self.folder_var,
            width=300
        )
        folder_entry.pack(side="left", padx=5)
        
        browse_btn = ctk.CTkButton(
            folder_frame,
            text="Browse",
            width=70,
            command=self._browse_folder
        )
        browse_btn.pack(side="left", padx=5)
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
        
        ctk.CTkLabel(thread_frame, text="Download Threads (Regular Downloads):").pack(
            side="left", padx=5
        )
        
        self.thread_var = ctk.IntVar(value=4)
        thread_slider = ctk.CTkSlider(
            thread_frame,
            from_=1,
            to=8,
            number_of_steps=7,
            variable=self.thread_var,
            command=self._on_thread_change
        )
        thread_slider.pack(side="left", expand=True, padx=5)
        
        thread_label = ctk.CTkLabel(thread_frame, textvariable=self.thread_var)
        thread_label.pack(side="left", padx=5)
        logger.debug(f"Initial thread count: {self.thread_var.get()}")
        
        # YouTube format selection
        logger.debug("Creating YouTube format selection")
        format_frame = ctk.CTkFrame(self)
        format_frame.pack(fill="x", padx=10, pady=5)
        
        # Create inner frame to maintain order of elements
        inner_frame = ctk.CTkFrame(format_frame, fg_color="transparent")
        inner_frame.pack(fill="x", padx=0, pady=0)
        
        # Audio only toggle
        self.audio_only = ctk.BooleanVar(value=False)
        audio_only_check = ctk.CTkCheckBox(
            inner_frame,
            text="Audio Only",
            variable=self.audio_only,
            command=self._on_audio_only_toggle
        )
        audio_only_check.pack(anchor="w", padx=5, pady=2)
        logger.debug(f"Initial audio only: {self.audio_only.get()}")
        
        # Audio quality
        audio_frame = ctk.CTkFrame(inner_frame)
        audio_frame.pack(fill="x", pady=2)
        
        ctk.CTkLabel(audio_frame, text="Audio Quality:").pack(
            side="left", padx=5
        )
        
        # Get audio quality options from YouTubeDownloader
        audio_qualities = list(YouTubeDownloader.AUDIO_FORMATS.keys())
        self.audio_quality = ctk.StringVar(value="High (m4a)")
        audio_menu = ctk.CTkOptionMenu(
            audio_frame,
            values=audio_qualities,
            variable=self.audio_quality,
            command=self._on_format_change
        )
        audio_menu.pack(side="left", padx=5)
        logger.debug(f"Initial audio quality: {self.audio_quality.get()}")
        
        # Video quality
        self.quality_frame = ctk.CTkFrame(inner_frame)
        self.quality_frame.pack(fill="x", pady=2)
        
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
        
    def _on_audio_only_toggle(self):
        """Handle audio only toggle"""
        is_audio_only = self.audio_only.get()
        logger.debug(f"Audio only toggled: {is_audio_only}")
        
        if is_audio_only:
            self.quality_frame.pack_forget()
        else:
            # Simply pack at the end of inner_frame, which maintains order
            self.quality_frame.pack(fill="x", pady=2)
            
        if self.on_format_change:
            self.on_format_change()
            
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
            f"Audio Only: {self.audio_only.get()}"
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
            'audio_only': self.audio_only.get()
        }
        logger.debug(f"Current settings: {settings}")
        return settings

    def get_max_downloads(self) -> int:
        """Get current max downloads setting"""
        try:
            return int(self.max_downloads_var.get())
        except ValueError:
            return 4
