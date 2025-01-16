import customtkinter as ctk
from typing import Dict
from pathlib import Path
import threading
import queue
from queue import Empty  # Import Empty from queue module
import multiprocessing as mp
import time
import tkinter.messagebox as messagebox
from tkinter import Tk
from typing import Optional

from utils.logger import Logger
from .settings_panel import SettingsPanel
from .download_widget import DownloadWidget
from downloader.process_pool import ProcessPool
from downloader.file_downloader import FileDownloader
from downloader.youtube_downloader import YouTubeDownloader
from downloader.utils import is_youtube_url, get_filename_from_url, ensure_unique_path

logger = Logger.get_logger(__name__)

class MainWindow:
    def __init__(self):
        logger.info("Initializing main window")
        
        # Set theme
        logger.debug("Setting customtkinter theme")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Create main window
        logger.debug("Creating main window")
        self.root = ctk.CTk()
        self.root.title("JustDownloadIt")
        self.root.geometry("600x800")
        
        # Create main frame with 3 sections
        logger.debug("Creating main frame")
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 1. URL input (top section)
        logger.debug("Creating URL input section")
        url_frame = ctk.CTkFrame(main_frame)
        url_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(url_frame, text="URLs (one per line)").pack(
            anchor="w", pady=(5,0)
        )
        
        self.url_text = ctk.CTkTextbox(url_frame, height=100)
        self.url_text.pack(fill="x", pady=(5,5))
        
        # 2. Settings panel (middle section)
        logger.debug("Creating settings panel")
        self.settings = SettingsPanel(
            main_frame,
            on_folder_change=self._on_folder_change,
            on_threads_change=self._on_threads_change,
            on_format_change=self._on_format_change
        )
        self.settings.pack(fill="x")
        
        # Initialize process pool with settings thread count
        initial_threads = self.settings.thread_var.get()
        logger.debug(f"Creating process pool with {initial_threads} threads")
        self.process_pool = ProcessPool(max_processes=initial_threads)
        
        # Track active and pending downloads
        self.active_downloads = set()
        self.pending_downloads = []  # List of (url, settings) tuples
        
        # Download button
        logger.debug("Creating download button")
        self.download_btn = ctk.CTkButton(
            main_frame,
            text="Start Download",
            command=self._start_downloads
        )
        self.download_btn.pack(fill="x", padx=10, pady=10)
        
        # 3. Downloads area (bottom section, scrollable)
        logger.debug("Creating downloads area")
        downloads_container = ctk.CTkFrame(main_frame)
        downloads_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Title bar for downloads
        downloads_title = ctk.CTkFrame(downloads_container)
        downloads_title.pack(fill="x", padx=5, pady=(5,0))
        
        ctk.CTkLabel(
            downloads_title,
            text="Downloads",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", pady=5)
        
        # Clear completed button
        self.clear_btn = ctk.CTkButton(
            downloads_title,
            text="Clear Completed",
            width=100,
            command=self._clear_completed
        )
        self.clear_btn.pack(side="right", padx=5)
        
        # Scrollable frame for download widgets
        self.downloads_frame = ctk.CTkScrollableFrame(
            downloads_container,
            label_text=""
        )
        self.downloads_frame.pack(fill="both", expand=True, padx=5, pady=(5,5))
        
        # Store active downloads
        self.downloads: Dict[str, DownloadWidget] = {}
        
        # Progress update queue
        logger.debug("Creating progress update queue")
        self.progress_queue = queue.Queue()
        self._start_progress_thread()
        
        # Window close handler
        logger.debug("Setting up window close handler")
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        logger.info("Main window initialization complete")
        
    def _show_error(self, title: str, message: str):
        """Show error dialog"""
        logger.debug(f"Showing error dialog - {title}: {message}")
        messagebox.showerror(title, message)
        
    def _clear_completed(self):
        """Clear completed downloads"""
        to_remove = []
        for widget_id, widget in list(self.downloads.items()):
            try:
                if not widget.winfo_exists() or hasattr(widget, '_destroyed'):
                    to_remove.append(widget_id)
            except Exception:
                # If we can't check widget existence, assume it's dead
                to_remove.append(widget_id)
                
        for widget_id in to_remove:
            self._remove_download_widget(widget_id)
            
    def _start_progress_thread(self):
        """Start thread to handle progress updates"""
        self._update_progress()
        
    def _update_progress(self):
        """Update progress for all downloads"""
        try:
            # Process all queued progress updates
            while True:
                try:
                    widget_id, source, progress_data = self.progress_queue.get_nowait()
                    if widget_id in self.downloads:
                        try:
                            widget = self.downloads[widget_id]
                            widget.update_progress(progress_data)
                            self.root.update_idletasks()  # Force immediate update
                        except Exception as e:
                            logger.error(f"Error updating widget {widget_id}: {str(e)}", exc_info=True)
                except Empty:
                    break
                    
        except Exception as e:
            logger.error(f"Error in progress update: {str(e)}", exc_info=True)
            
        finally:
            # Schedule next update if window still exists
            if self.root.winfo_exists():
                self.root.after(50, self._update_progress)
                
    def _remove_download_widget(self, widget_id: str):
        """Remove download widget"""
        try:
            if widget_id in self.downloads:
                logger.debug(f"Removing widget {widget_id}")
                widget = self.downloads[widget_id]
                
                # Remove from downloads dict before destroying
                # to prevent any updates during destruction
                del self.downloads[widget_id]
                
                # Destroy widget safely
                try:
                    widget.destroy()
                except Exception as e:
                    logger.error(f"Error destroying widget: {str(e)}", exc_info=True)
                
                # Update scrollregion
                self.downloads_frame.update_idletasks()
                
        except Exception as e:
            logger.error(f"Error removing widget {widget_id}: {str(e)}", exc_info=True)
            
    def _create_download_widget(self, title: str) -> str:
        """Create a new download widget"""
        logger.info(f"Creating download widget for: {title}")
        
        # Create widget
        widget = DownloadWidget(
            self.downloads_frame,
            title=title,
            on_cancel=self._cancel_download
        )
        widget.pack(fill="x", padx=5, pady=2)
        
        # Store widget
        self.downloads[widget.id] = widget
        logger.info(f"Download widget created: {widget.id}")
        
        return widget.id
        
    def _cancel_download(self, widget_id: str):
        """Cancel download process"""
        try:
            logger.info(f"Cancelling download for widget {widget_id}")
            if widget_id in self.downloads:
                widget = self.downloads[widget_id]
                self.process_pool.terminate_process(widget_id)
                widget.set_status("Download cancelled")
        except Exception as e:
            logger.error(f"Error cancelling download: {str(e)}", exc_info=True)
            if widget_id in self.downloads:
                self.downloads[widget_id].set_status("Error cancelling download")
            
    def _download_file(self, url: str, settings: dict):
        """Download regular file"""
        try:
            # Create download widget
            filename = get_filename_from_url(url)
            widget = DownloadWidget(
                self.downloads_frame,
                url=url,
                title=filename,
                on_cancel=lambda: self._cancel_download(widget.id),
                on_clear=lambda: self._clear_download(widget.id)
            )
            widget.pack(fill="x", padx=5, pady=2)
            
            # Create a queue for progress updates
            progress_queue = mp.Queue()
            
            # Store widget before starting process
            self.downloads[widget.id] = widget
            
            # Show audio progress bar for regular downloads
            widget.show_audio_progress()
            
            # Start download process
            process_id = self.process_pool.start_process(
                FileDownloader.download,
                args=(url, str(settings['download_folder']), progress_queue)
            )
            
            # Store process ID in widget
            self.active_downloads.add(process_id)
            
            # Start monitoring progress
            threading.Thread(
                target=self._monitor_download_progress,
                args=(widget, process_id, progress_queue),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"Download error: {str(e)}", exc_info=True)
            self._show_error(
                "Error",
                f"Failed to start download: {str(e)}"
            )
            
    def _download_youtube(self, url: str, settings: dict):
        """Download YouTube video"""
        try:
            # Create download widget
            info = YouTubeDownloader.get_video_info(url)
            widget = DownloadWidget(
                self.downloads_frame,
                url=url,
                title=info['title'],
                on_cancel=lambda: self._cancel_download(widget.id),
                on_clear=lambda: self._clear_download(widget.id)
            )
            widget.pack(fill="x", padx=5, pady=2)
            
            # Create a queue for progress updates
            progress_queue = mp.Queue()
            
            # Store widget before starting process
            self.downloads[widget.id] = widget
            
            # Get settings
            dest_folder = str(settings['download_folder'])
            video_quality = settings['video_quality']
            audio_quality = settings['audio_quality']
            audio_only = settings['audio_only']
            
            # Show appropriate progress bars
            widget.show_audio_progress()  # Always show audio progress
            if not audio_only:
                widget.show_video_progress()  # Only show video progress if not audio-only
            
            # Start download process
            process_id = self.process_pool.start_process(
                YouTubeDownloader.download_process,
                args=(url, dest_folder, video_quality, audio_quality, audio_only, progress_queue)
            )
            
            # Store process ID in widget
            self.active_downloads.add(process_id)
            
            # Start monitoring progress
            threading.Thread(
                target=self._monitor_youtube_progress,
                args=(widget, process_id, progress_queue, not audio_only),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"Failed to start YouTube download: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Failed to start download: {str(e)}")
            
    def _monitor_youtube_progress(
        self,
        widget: DownloadWidget,
        process_id: str,
        progress_queue: mp.Queue,
        has_video: bool
    ):
        """Monitor progress of YouTube download"""
        try:
            while process_id in self.active_downloads:
                try:
                    # Try to get progress update
                    progress = progress_queue.get(timeout=0.1)
                    
                    if progress['type'] == 'video_progress':
                        widget.update_video_progress(**progress['data'])
                    elif progress['type'] == 'audio_progress':
                        widget.update_audio_progress(**progress['data'])
                    elif progress['type'] == 'muxing_progress':
                        widget.show_muxing_progress()
                        widget.update_muxing_progress(**progress['data'])
                    elif progress['type'] == 'error':
                        logger.error(f"Download error: {progress['error']}")
                        widget.set_status(f"Error: {progress['error']}")
                        self.active_downloads.remove(process_id)
                        # Check pending downloads
                        self._check_pending_downloads()
                        return
                    elif progress['type'] == 'complete':
                        logger.info("Download completed successfully")
                        widget.set_status("Download complete!")
                        self.active_downloads.remove(process_id)
                        # Check pending downloads
                        self._check_pending_downloads()
                        return
                        
                except queue.Empty:
                    # No progress update available
                    continue
                except Exception as e:
                    logger.error(f"Error monitoring progress: {str(e)}", exc_info=True)
                    widget.set_status(f"Error: {str(e)}")
                    self.active_downloads.remove(process_id)
                    # Check pending downloads
                    self._check_pending_downloads()
                    return
                    
        except Exception as e:
            logger.error(f"Monitor thread failed: {str(e)}", exc_info=True)
            widget.set_status(f"Error: {str(e)}")
            if process_id in self.active_downloads:
                self.active_downloads.remove(process_id)
                # Check pending downloads
                self._check_pending_downloads()
                
    def _monitor_download_progress(
        self,
        widget: DownloadWidget,
        process_id: str,
        progress_queue: mp.Queue
    ):
        """Monitor progress of file download"""
        try:
            # Show audio progress bar since we're downloading a single file
            widget.show_audio_progress()
            
            while process_id in self.active_downloads:
                try:
                    # Try to get progress update
                    progress = progress_queue.get(timeout=0.1)
                    
                    if progress['type'] == 'progress':
                        data = progress['data']
                        widget.update_audio_progress(
                            data['progress'],
                            data['speed'],
                            data['downloaded'],
                            data['total']
                        )
                    elif progress['type'] == 'complete':
                        widget.set_status("Download complete!")
                        self.active_downloads.remove(process_id)
                        # Check pending downloads
                        self._check_pending_downloads()
                        break
                    elif progress['type'] == 'error':
                        widget.set_status(f"Error: {progress.get('error', 'Unknown error')}")
                        self.active_downloads.remove(process_id)
                        # Check pending downloads
                        self._check_pending_downloads()
                        break
                        
                except queue.Empty:
                    # No progress update available
                    continue
                except Exception as e:
                    logger.error(f"Error monitoring progress: {str(e)}", exc_info=True)
                    widget.set_status(f"Error: {str(e)}")
                    self.active_downloads.remove(process_id)
                    # Check pending downloads
                    self._check_pending_downloads()
                    break
                    
        except Exception as e:
            logger.error(f"Monitor thread failed: {str(e)}", exc_info=True)
            widget.set_status(f"Error: {str(e)}")
            if process_id in self.active_downloads:
                self.active_downloads.remove(process_id)
                # Check pending downloads
                self._check_pending_downloads()
                
    def _clear_download(self, process_id: str):
        """Remove a download from active downloads"""
        if process_id in self.active_downloads:
            self.active_downloads.remove(process_id)
            logger.debug(f"Cleared download {process_id}")
            
    def _check_pending_downloads(self):
        """Check if there are pending downloads that can be started"""
        while len(self.active_downloads) < self.process_pool.max_processes and self.pending_downloads:
            url, settings = self.pending_downloads.pop(0)
            try:
                if is_youtube_url(url):
                    self._download_youtube(url, settings)
                else:
                    self._download_file(url, settings)
            except Exception as e:
                logger.error(f"Error starting pending download {url}: {str(e)}", exc_info=True)
                messagebox.showerror("Error", f"Failed to start download: {str(e)}")
        
        # Schedule next check if there are still pending downloads
        if self.pending_downloads:
            self.root.after(1000, self._check_pending_downloads)
            
    def _start_downloads(self):
        """Start downloading all URLs"""
        try:
            # Get URLs from text box
            urls = [url.strip() for url in self.url_text.get("1.0", "end").split("\n") if url.strip()]
            if not urls:
                return
                
            # Clear URL text box
            self.url_text.delete("1.0", "end")
            
            # Get current settings
            settings = {
                'download_folder': self.settings.folder_var.get(),
                'video_quality': self.settings.video_quality.get(),
                'audio_quality': self.settings.audio_quality.get(),
                'audio_only': self.settings.audio_only.get()
            }
            
            # Process each URL
            for url in urls:
                # Check if this is a playlist
                if "list=" in url:
                    try:
                        # Get all video URLs from playlist
                        playlist_urls = YouTubeDownloader.get_playlist_urls(url)
                        if playlist_urls:
                            # Add each video URL back to the text box
                            for video_url in playlist_urls:
                                self.url_text.insert("end", video_url + "\n")
                        else:
                            messagebox.showwarning("Warning", "No videos found in playlist")
                        continue  # Skip processing this URL as we've expanded it
                    except Exception as e:
                        logger.error(f"Failed to get playlist info: {str(e)}", exc_info=True)
                        messagebox.showerror("Error", f"Failed to get playlist info: {str(e)}")
                        continue
                        
                # Try to start download or queue it
                if len(self.active_downloads) < self.process_pool.max_processes:
                    # Start download immediately
                    if is_youtube_url(url):
                        self._download_youtube(url, settings)
                    else:
                        self._download_file(url, settings)
                else:
                    # Queue download for later
                    self.pending_downloads.append((url, settings.copy()))
                    logger.debug(f"Queued download for later: {url}")
                    
            # Start checking for pending downloads
            if self.pending_downloads:
                self.root.after(1000, self._check_pending_downloads)
                
        except Exception as e:
            logger.error(f"Error starting downloads: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Failed to start downloads: {str(e)}")
            
    def _on_folder_change(self, folder: Path):
        """Handle download folder change"""
        pass  # Nothing to do, folder is stored in settings
        
    def _on_threads_change(self, threads: int):
        """Handle threads count change"""
        self.process_pool.max_processes = threads
        
    def _on_format_change(self):
        """Handle format change"""
        pass  # Nothing to do, formats are stored in settings
        
    def _on_closing(self):
        """Handle window closing"""
        if self.active_downloads:
            if messagebox.askokcancel(
                "Quit",
                "There are active downloads. Do you want to quit and cancel all downloads?"
            ):
                # Terminate all processes
                self.process_pool.terminate_all()
                self.root.destroy()
        else:
            self.root.destroy()
            
    def run(self):
        """Start the application"""
        self.root.mainloop()
