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
import requests

from utils.logger import Logger
from .settings_panel import SettingsPanel
from .download_widget import DownloadWidget
from downloader.process_pool import ProcessPool
from downloader.file_downloader import FileDownloader
from downloader.youtube_downloader import YouTubeDownloader
from downloader.utils import is_youtube_url, get_filename_from_url, ensure_unique_path

logger = Logger.get_logger(__name__)

class ResizerFrame(ctk.CTkFrame):
    def __init__(self, master, resized_widget, **kwargs):
        super().__init__(master, height=5, **kwargs)
        self.resized_widget = resized_widget
        self.start_y = None
        self.initial_height = None
        self.last_widget_height = None
        self.initial_window_height = None
        self.current_height = 125  # Track the actual height we set
        
        # Scale factor to reduce movement (1/1.25)
        self.scaling = 0.8
        
        # Configure appearance
        self.configure(fg_color="gray30", cursor="sb_v_double_arrow")
        
        # Ensure resized widget maintains its size
        self.resized_widget.pack_propagate(False)
        
        # Bind mouse events
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        
        # For smoother updates
        self._update_after_id = None
        
    def _on_press(self, event):
        self.start_y = event.y_root
        # Use our tracked height instead of winfo_height
        self.initial_height = self.current_height
        self.initial_window_height = self.winfo_toplevel().winfo_height()

    def _on_drag(self, event):
        if self.start_y is None:
            return

        # Calculate raw delta from mouse movement
        delta = event.y_root - self.start_y
        
        # Scale the movement delta and add to initial height
        scaled_delta = int(delta * self.scaling)
        new_height = max(50, self.initial_height + scaled_delta)
        
        # Update URL field height and track it
        self.current_height = new_height
        self.resized_widget.configure(height=new_height)
        self.resized_widget.update_idletasks()
        
    def _on_release(self, event):
        if self.start_y is None:
            return
            
        # Cancel any pending updates
        if self._update_after_id:
            self.after_cancel(self._update_after_id)
            
        # Reset everything
        self.start_y = None
        self.initial_height = None
        self.last_delta = 0
        
        # Re-enable and update settings panel
        main_window = self.winfo_toplevel()
        if hasattr(main_window, 'settings_panel'):
            main_window.settings_panel.pack(fill="x", padx=10, pady=5)
            self._update_layout()
            
    def _update_layout(self):
        """Update layout with less flickering"""
        self._update_after_id = None
        main_window = self.winfo_toplevel()
        if hasattr(main_window, 'settings_panel'):
            main_window.update_idletasks()
            
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
        self.root.update_idletasks()  # Force geometry update
        
        # Create main frame with 3 sections
        logger.debug("Creating main frame")
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 1. URL input (top section)
        logger.debug("Creating URL input section")
        self.url_frame = ctk.CTkFrame(main_frame)
        self.url_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(self.url_frame, text="URLs (one per line)").pack(
            anchor="w", pady=(5,0)
        )
        
        # Create a container frame to control height
        text_container = ctk.CTkFrame(self.url_frame)
        text_container.pack(fill="x", pady=(5,0))
        text_container.pack_propagate(False)  # Prevent propagation of size changes
        
        # Create the text box with explicit height
        self.url_text = ctk.CTkTextbox(text_container, height=125)
        self.url_text.pack(fill="both", expand=True)
        
        # Set container height to match textbox
        text_container.configure(height=125)
        
        # Add resizer frame
        self.resizer = ResizerFrame(self.url_frame, text_container)  # Change to use container instead of textbox
        self.resizer.pack(fill="x", pady=(2,5))
        
        # Bind text change event to update button text
        self.url_text.bind('<<Modified>>', self._on_url_text_changed)
        
        # 2. Settings panel (middle section)
        logger.debug("Creating settings panel")
        self.settings_panel = SettingsPanel(
            main_frame,
            on_folder_change=self._on_folder_change,
            on_threads_change=self._on_threads_change,
            on_format_change=self._on_format_change,
            on_max_downloads_change=self._on_max_downloads_change
        )
        self.settings_panel.pack(fill="x", padx=10, pady=5)
        
        # Initialize process pool with settings panel value
        self.process_pool = ProcessPool(max_processes=int(self.settings_panel.max_downloads_var.get()))
        self.download_threads = self.settings_panel.thread_var.get()
        
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
                if widget.is_completed:
                    to_remove.append(widget_id)
            except Exception:
                continue
            
        for widget_id in to_remove:
            self._remove_download_widget(widget_id)
            
    def _start_progress_thread(self):
        """Start thread to handle progress updates"""
        self._update_progress()
        
    def _update_progress(self):
        """Update progress for all downloads"""
        try:
            updates = []
            # Process all queued progress updates
            while True:
                try:
                    # Collect up to 100 updates at a time to prevent overwhelming the GUI
                    if len(updates) >= 100:
                        break
                    widget_id, source, progress_data = self.progress_queue.get_nowait()
                    updates.append((widget_id, source, progress_data))
                except Empty:
                    break
                    
            # Apply all updates in a batch
            if updates:
                for widget_id, source, progress_data in updates:
                    if widget_id in self.downloads:
                        try:
                            widget = self.downloads[widget_id]
                            widget.update_progress(progress_data)
                        except Exception as e:
                            logger.error(f"Error updating widget {widget_id}: {str(e)}", exc_info=True)
                
                # Only update GUI once after all updates are processed
                self.root.update_idletasks()
            
        except Exception as e:
            logger.error(f"Error in progress update: {str(e)}", exc_info=True)
            
        finally:
            # Schedule next update
            if self.root.winfo_exists():
                # Use longer interval if no updates to process
                next_interval = 10 if not updates else 50
                self.root.after(next_interval, self._update_progress)
                
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
            
            try:
                # Start download process
                process_id = self.process_pool.start_process(
                    FileDownloader.download,
                    args=(url, str(settings['download_folder']), progress_queue, self.download_threads)
                )
                
                # Store process ID in widget
                self.active_downloads.add(process_id)
                
                # Start monitoring progress
                threading.Thread(
                    target=self._monitor_download_progress,
                    args=(widget, process_id, progress_queue),
                    daemon=True
                ).start()
                
            except RuntimeError as e:
                if "Maximum number of processes" in str(e):
                    self.pending_downloads.append((url, settings.copy()))
                    widget.set_status("Queued - waiting for available slot...")
                    logger.debug(f"Queued download for later: {url}")
                    self.root.after(1000, self._check_pending_downloads)
                    return  # Return early to avoid outer exception handler
                else:
                    raise
                
        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to URL: {url}", exc_info=True)
            messagebox.showerror("Connection Error", f"Could not connect to {url}. Please check if the URL is correct and accessible.")
            if widget.id in self.downloads:
                self._remove_download_widget(widget.id)
        except Exception as e:
            logger.error(f"Failed to start download: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Failed to start download: {str(e)}")
            if widget.id in self.downloads:
                self._remove_download_widget(widget.id)
                
    def _download_youtube(self, url: str, settings: dict):
        """Download YouTube video"""
        try:
            # Create download widget with just the URL initially
            widget = DownloadWidget(
                self.downloads_frame,
                url=url,
                title=url,  # Use URL as initial title
                on_cancel=lambda: self._cancel_download(widget.id),
                on_clear=lambda: self._clear_download(widget.id)
            )
            widget.pack(fill="x", padx=5, pady=2)
            
            # Create a queue for progress updates
            progress_queue = mp.Queue()
            
            # Store widget before starting process
            self.downloads[widget.id] = widget
            
            try:
                # Start download process - video info will be gathered in the process
                process_id = self.process_pool.start_process(
                    YouTubeDownloader.download_process,
                    args=(url, str(settings['download_folder']), settings['video_quality'],
                          settings['audio_quality'], settings['audio_only'], progress_queue)
                )
                
                # Store process ID in widget
                self.active_downloads.add(process_id)
                
                # Start monitoring progress
                threading.Thread(
                    target=self._monitor_youtube_progress,
                    args=(widget, process_id, progress_queue, not settings['audio_only']),
                    daemon=True
                ).start()
                
            except RuntimeError as e:
                if "Maximum number of processes" in str(e):
                    self.pending_downloads.append((url, settings.copy()))
                    widget.set_status("Queued - waiting for available slot...")
                    logger.debug(f"Queued download for later: {url}")
                    self.root.after(1000, self._check_pending_downloads)
                    return
                else:
                    raise
                
        except Exception as e:
            logger.error(f"Failed to start download: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Failed to start download: {str(e)}")
            if widget.id in self.downloads:
                self._remove_download_widget(widget.id)
                
    def _monitor_youtube_progress(
        self,
        widget: DownloadWidget,
        process_id: str,
        progress_queue: mp.Queue,
        has_video: bool
    ):
        """Monitor progress of YouTube download"""
        try:
            # Show appropriate progress bars
            widget.show_audio_progress()  # Always show audio progress
            if has_video:
                widget.show_video_progress()  # Only show video progress if not audio-only
                
            while True:
                try:
                    progress = progress_queue.get(timeout=0.1)
                    
                    if progress['type'] == 'title':
                        # Update widget title when we get video info
                        widget.update_title(progress['title'])
                    elif progress['type'] == 'video_progress':
                        widget.update_video_progress(
                            progress['data']['progress'],
                            progress['data']['speed'],
                            progress['data']['downloaded'],
                            progress['data']['total']
                        )
                    elif progress['type'] == 'audio_progress':
                        widget.update_audio_progress(
                            progress['data']['progress'],
                            progress['data']['speed'],
                            progress['data']['downloaded'],
                            progress['data']['total']
                        )
                    elif progress['type'] == 'muxing_progress':
                        widget.show_muxing_progress()
                        widget.update_muxing_progress(
                            progress['data']['progress'],
                            progress['data']['status']
                        )
                    elif progress['type'] == 'error':
                        widget.set_status(f"Error: {progress['error']}")
                        self._clear_download(process_id)
                        break
                    elif progress['type'] == 'complete':
                        widget.set_status("Download complete")
                        widget.is_completed = True
                        widget.is_cancelled = True
                        widget.cancel_btn.configure(text="Clear")
                        self._clear_download(process_id)
                        break
                        
                except queue.Empty:
                    # Check if process is still running
                    if not self.process_pool.is_process_running(process_id):
                        widget.set_status("Download failed")
                        self._clear_download(process_id)
                        break
                        
        except Exception as e:
            logger.error(f"Error monitoring progress: {str(e)}", exc_info=True)
            widget.set_status(f"Error: {str(e)}")
            self._clear_download(process_id)
            
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
            
            last_update_time = 0
            MIN_UPDATE_INTERVAL = 0.05  # Minimum 50ms between updates
            
            while process_id in self.active_downloads:
                try:
                    # Try to get progress update
                    progress = progress_queue.get(timeout=0.5)  # Longer timeout to reduce CPU usage
                    
                    current_time = time.time()
                    if progress['type'] == 'progress':
                        # Only forward progress updates if enough time has passed
                        if current_time - last_update_time >= MIN_UPDATE_INTERVAL:
                            data = progress['data']
                            widget.update_audio_progress(
                                data['progress'],
                                data['speed'],
                                data['downloaded'],
                                data['total']
                            )
                            last_update_time = current_time
                    elif progress['type'] == 'complete':
                        widget.set_status("Download complete")
                        widget.is_completed = True
                        widget.is_cancelled = True
                        widget.cancel_btn.configure(text="Clear")
                        self._clear_download(process_id)
                        break
                    elif progress['type'] == 'error':
                        widget.set_status(f"Error: {progress.get('error', 'Unknown error')}")
                        self._clear_download(process_id)
                        break
                        
                except queue.Empty:
                    # No progress update available, just continue
                    continue
                except Exception as e:
                    logger.error(f"Error monitoring progress: {str(e)}", exc_info=True)
                    widget.set_status(f"Error: {str(e)}")
                    self._clear_download(process_id)
                    break
                    
        except Exception as e:
            logger.error(f"Error monitoring progress: {str(e)}", exc_info=True)
            widget.set_status(f"Error: {str(e)}")
            self._clear_download(process_id)
            
    def _clear_download(self, process_id: str):
        """Remove a download from active downloads"""
        if process_id in self.active_downloads:
            self.active_downloads.remove(process_id)
            logger.debug(f"Cleared download {process_id}")
            
    def _check_pending_downloads(self):
        """Check if there are pending downloads that can be started"""
        # Clean up completed processes first
        self.process_pool.cleanup_completed()
        
        # Now check how many active processes we have
        active_processes = len([p for p in self.process_pool.processes.values() if p.is_alive()])

        while active_processes < self.process_pool.max_processes and self.pending_downloads:
            url, settings = self.pending_downloads.pop(0)
            try:
                if is_youtube_url(url):
                    self._download_youtube(url, settings)
                else:
                    self._download_file(url, settings)
            except Exception as e:
                logger.error(f"Error starting pending download {url}: {str(e)}", exc_info=True)
                messagebox.showerror("Error", f"Failed to start download: {str(e)}")
            
            # Recalculate active processes after starting a download
            active_processes = len([p for p in self.process_pool.processes.values() if p.is_alive()])

        # Schedule next check if there are still pending downloads
        if self.pending_downloads:
            self.root.after(1000, self._check_pending_downloads)
            
    def _process_next_url(self, urls, settings, remaining_urls):
        """Process next URL in the list asynchronously"""
        if not urls:
            # All URLs processed, update text box with remaining URLs
            self.url_text.delete("1.0", "end")
            if remaining_urls:
                for url in remaining_urls:
                    self.url_text.insert("end", url + "\n")
            return
            
        # Get next URL
        url = urls.pop(0)
        
        # Skip anything that doesn't look like a URL
        if '.' not in url or not all(p.strip() for p in url.split('.')):
            remaining_urls.append(url)
            # Process next URL after a short delay
            self.root.after(1, lambda: self._process_next_url(urls, settings, remaining_urls))
            return
            
        # Try to validate URL in a separate thread
        def validate_url():
            try:
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                })
                response = session.head(url if url.startswith(('http://', 'https://')) else f'https://{url}', timeout=5)
                response.raise_for_status()
                
                # URL is valid, start or queue download
                self.root.after(1, lambda: self._start_single_download(url, settings.copy()))
                
            except Exception as e:
                logger.debug(f"Skipping invalid URL {url}")
                remaining_urls.append(url)
                
            # Process next URL after validation
            self.root.after(1, lambda: self._process_next_url(urls, settings, remaining_urls))
            
        threading.Thread(target=validate_url, daemon=True).start()
        
    def _start_single_download(self, url: str, settings: dict):
        """Start or queue a single download"""
        if len(self.active_downloads) < self.process_pool.max_processes:
            # Start download immediately
            if is_youtube_url(url):
                self._download_youtube(url, settings)
            else:
                self._download_file(url, settings)
        else:
            # Queue download for later
            self.pending_downloads.append((url, settings))
            logger.debug(f"Queued download for later: {url}")
            # Start checking for pending downloads
            self.root.after(1000, self._check_pending_downloads)

    def _start_downloads(self):
        """Start downloading all URLs"""
        try:
            # Get URLs from text box
            all_urls = [url.strip() for url in self.url_text.get("1.0", "end").split("\n") if url.strip()]
            if not all_urls:
                return
            
            # Check if there are any playlist URLs
            has_playlists = any("list=" in url for url in all_urls)
            
            if has_playlists:
                # Only handle playlists, keep other URLs in the text field
                remaining_urls = []
                extracted_videos = []
                
                for url in all_urls:
                    if "list=" in url:
                        try:
                            playlist_urls = YouTubeDownloader.get_playlist_urls(url)
                            if playlist_urls:
                                logger.info(f"Found {len(playlist_urls)} videos in playlist")
                                extracted_videos.extend(playlist_urls)
                            else:
                                logger.debug(f"No videos found in playlist: {url}")
                                remaining_urls.append(url)
                        except Exception as e:
                            logger.debug(f"Failed to get playlist info: {str(e)}")
                            remaining_urls.append(url)
                    else:
                        remaining_urls.append(url)
                
                # Update text box with remaining URLs and extracted videos
                self.url_text.delete("1.0", "end")
                for url in remaining_urls + extracted_videos:
                    self.url_text.insert("end", url + "\n")
                return
                
            # Get current settings
            settings = {
                'download_folder': self.settings_panel.folder_var.get(),
                'video_quality': self.settings_panel.video_quality.get(),
                'audio_quality': self.settings_panel.audio_quality.get(),
                'audio_only': self.settings_panel.audio_only.get()
            }
            
            # Start processing URLs asynchronously
            self._process_next_url(all_urls.copy(), settings, [])
            
        except Exception as e:
            logger.error(f"Error starting downloads: {str(e)}", exc_info=True)
            
    def _on_folder_change(self, folder: Path):
        """Handle download folder change"""
        pass  # Nothing to do, folder is stored in settings
        
    def _on_threads_change(self, threads: int):
        """Handle threads count change"""
        logger.info(f"Updating download threads to: {threads}")
        self.download_threads = threads
        
    def _on_format_change(self):
        """Handle format change"""
        pass  # Nothing to do, formats are stored in settings
        
    def _on_max_downloads_change(self, value: int):
        """Handle max downloads setting change"""
        logger.debug(f"Max downloads changed to {value}")
        self.process_pool.max_processes = int(value)
        
    def _on_closing(self):
        """Handle window closing"""
        try:
            # Clean up all running processes
            logger.info("Cleaning up processes before exit")
            self.process_pool.cleanup()
            
            # Destroy the window
            logger.info("Destroying main window")
            self.root.destroy()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}", exc_info=True)
            self.root.destroy()  # Ensure window is destroyed even if cleanup fails
            
    def _on_url_text_changed(self, event=None):
        """Handle URL text content changes"""
        try:
            # Reset modified flag (required for <<Modified>> event to work properly)
            self.url_text.edit_modified(False)
            
            # Check content for playlist URLs
            urls = [url.strip() for url in self.url_text.get("1.0", "end").split("\n") if url.strip()]
            has_playlists = any("list=" in url for url in urls)
            
            # Update button text
            self.download_btn.configure(
                text="Extract Playlists" if has_playlists else "Queue Downloads"
            )
        except Exception as e:
            logger.error(f"Error updating button text: {str(e)}", exc_info=True)
            
    def run(self):
        """Start the application"""
        self.root.mainloop()
