import customtkinter as ctk
from typing import Dict, List, Optional, Any
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
from utils.exceptions import DownloadError, YouTubeError, ProcessError, FFmpegError, JustDownloadItError
from utils.logger import Logger
from .settings_panel import SettingsPanel
from .download_widget import DownloadWidget
from downloader.process_pool import ProcessPool
from downloader.file_downloader import FileDownloader
from downloader.youtube_downloader import YouTubeDownloader
from utils import ensure_unique_path
from utils.utils_ui import is_youtube_url, get_filename_from_url
import uuid
import os

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
        try:
            logger.info("Initializing main window")
            
            # Set theme
            logger.debug("Setting customtkinter theme")
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            
            # Create main window
            logger.debug("Creating main window")
            self.root = ctk.CTk()
            self.root.title("JustDownloadIt")
            
            # Set minimum window size to prevent UI elements from being squished
            self.root.minsize(600, 600)
            
            # Set initial geometry to minimum width and reasonable height
            self.root.geometry("600x700")
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
            self.pending_downloads = []  # List of (widget_id, url, settings) tuples
            
            # Download button
            logger.debug("Creating download button")
            self.download_btn = ctk.CTkButton(
                main_frame,
                text="Start Downloads",
                command=self._start_downloads,
                fg_color="#2ea043",  # GitHub-style green
                hover_color="#2c974b",  # Darker green for hover
                text_color="black",
                font=("", 13, "bold")
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
                text="  Active Downloads:",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(side="left", pady=5)
            
            # Create button frame for right-aligned buttons
            button_frame = ctk.CTkFrame(downloads_title)
            button_frame.pack(side="right", padx=5)
            
            # Cancel All button (red)
            self.cancel_all_btn = ctk.CTkButton(
                button_frame,
                text="Cancel All",
                width=80,
                fg_color="#b22222",  # dark red
                hover_color="#8b0000",  # darker red
                command=self._cancel_all_downloads
            )
            self.cancel_all_btn.pack(side="right", padx=5)
            
            # Cancel Queued button
            self.cancel_queued_btn = ctk.CTkButton(
                button_frame,
                text="Cancel Queued",
                width=100,
                command=self._cancel_queued_downloads
            )
            self.cancel_queued_btn.pack(side="right", padx=5)
            
            # Clear Completed button
            self.clear_btn = ctk.CTkButton(
                button_frame,
                text="Clear Aborted/Completed",
                width=140,
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
            
            # Add status labels at the bottom
            status_container = ctk.CTkFrame(self.root, fg_color="transparent")
            status_container.pack(side="bottom", fill="x", pady=(0,5))
            
            # Center frame for labels
            center_frame = ctk.CTkFrame(status_container, fg_color="transparent")
            center_frame.pack(expand=True)
            
            # Queue label
            self.queue_label = ctk.CTkLabel(
                center_frame,
                text="Queue:",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            self.queue_label.pack(side="left", padx=(0,2))
            
            self.queue_count = ctk.CTkLabel(
                center_frame,
                text="0",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            self.queue_count.pack(side="left", padx=(0,20))

            # Active downloads label
            self.active_label = ctk.CTkLabel(
                center_frame,
                text="Active Downloads:",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            self.active_label.pack(side="left", padx=(0,2))
            
            self.active_count = ctk.CTkLabel(
                center_frame,
                text="0",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            self.active_count.pack(side="left")

            # Window close handler
            logger.debug("Setting up window close handler")
            self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
            
            logger.info("Main window initialization complete")
        except Exception as e:
            logger.error(f"Error initializing main window: {str(e)}", exc_info=True)
            raise JustDownloadItError(f"Error initializing main window: {str(e)}")
        
    def _show_error(self, title: str, message: str):
        """Show error dialog"""
        logger.debug(f"Showing error dialog - {title}: {message}")
        messagebox.showerror(title, message)
        
    def _clear_completed(self):
        """Clear completed downloads"""
        # Get list of completed downloads first to avoid modifying dict during iteration
        to_clear = []
        for widget_id, widget in self.downloads.items():
            if widget.is_completed or widget.is_cancelled:
                to_clear.append(widget_id)
                
        # Clear each completed/cancelled download
        for widget_id in to_clear:
            self._remove_download_widget(widget_id)
            
        # Update counts after clearing
        self._update_download_counts()
            
    def _remove_download_widget(self, widget_id: str):
        """Remove download widget"""
        try:
            logger.info(f"Removing download widget {widget_id}")
            if widget_id in self.downloads:
                # Get widget and process ID
                widget = self.downloads[widget_id]
                process_id = widget.process_id
                
                # Remove from active downloads if present
                if process_id and process_id in self.active_downloads:
                    self.active_downloads.remove(process_id)
                
                # Remove from pending downloads if present
                self.pending_downloads = [(wid, url, settings) for wid, url, settings in self.pending_downloads 
                                       if wid != widget_id]
                
                # Remove widget from UI
                widget.destroy()
                del self.downloads[widget_id]
                
                # Clean up process if it exists
                if process_id:
                    self._clear_download(process_id)
                    
                # Update counts after removal
                self._update_download_counts()
                    
        except Exception as e:
            logger.error(f"Error removing widget {widget_id}: {str(e)}", exc_info=True)
            
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
                
    def _create_download_widget(self, title: str, url: str = "", file_type: str = "file") -> str:
        """Create a new download widget"""
        logger.info(f"Creating download widget for: {title} (type: {file_type})")
        widget = DownloadWidget(
            self.downloads_frame,
            url=url,
            title=title,
            on_cancel=self._cancel_download,
            file_type=file_type
        )
        widget.pack(fill="x", padx=5, pady=2)
        self.downloads[widget.id] = widget
        logger.info(f"Download widget created: {widget.id}")
        return widget.id
        
    def _cancel_download(self, widget_id: str):
        """Cancel download process"""
        try:
            logger.info(f"Cancelling download for widget {widget_id}")
            if widget_id in self.downloads:
                widget = self.downloads[widget_id]
                if hasattr(widget, 'process_id'):  # Check if process ID exists
                    self.process_pool.terminate_process(widget.process_id)
                    widget.set_status("Download cancelled")
                    self._clear_download(widget.process_id)
        except Exception as e:
            logger.error(f"Error cancelling download: {str(e)}", exc_info=True)
            if widget_id in self.downloads:
                self.downloads[widget_id].set_status("Error cancelling download")
            
    def _download_file(self, widget_id: str, url: str, settings: dict):
        """Download regular file"""
        try:
            if widget_id not in self.downloads:
                logger.error(f"No widget found for ID: {widget_id}")
                return
            widget = self.downloads[widget_id]
            progress_queue = mp.Queue()
            try:
                process_id = self.process_pool.start_process(
                    FileDownloader.download,
                    args=(url, str(settings['download_folder']), progress_queue, self.download_threads)
                )
                self.active_downloads.add(process_id)
                widget.process_id = process_id
                threading.Thread(
                    target=self._monitor_download_progress,
                    args=(widget, process_id, progress_queue),
                    daemon=True
                ).start()
            except RuntimeError as e:
                if "Maximum number of processes" in str(e):
                    self.pending_downloads.append((widget_id, url, settings))
                    widget.set_status("Waiting for available slot...")
                    logger.debug(f"Queued download for later: {url}")
                    self._update_download_counts()
                    return
                raise
        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to URL: {url}", exc_info=True)
            messagebox.showerror("Connection Error", f"Could not connect to {url}. Please check if the URL is correct and accessible.")
        except Exception as e:
            logger.error(f"Failed to start download: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Failed to start download: {str(e)}")
            
    def _download_youtube(self, widget_id: str, url: str, settings: dict):
        """Download YouTube video"""
        try:
            # Get widget by ID
            if widget_id not in self.downloads:
                logger.error(f"No widget found for ID: {widget_id}")
                return
            widget = self.downloads[widget_id]
                
            # Create a queue for progress updates
            progress_queue = mp.Queue()
            
            try:
                # Start download process - video info will be gathered in the process
                process_id = self.process_pool.start_process(
                    YouTubeDownloader.download_process,
                    args=(url, str(settings['download_folder']), settings['video_quality'],
                          settings['audio_quality'], settings['audio_enabled'], settings['video_enabled'], 
                          settings['muxing_enabled'], progress_queue)
                )
                
                # Store process ID in widget
                self.active_downloads.add(process_id)
                widget.process_id = process_id  # Store process ID in widget for cancellation
                
                # Start monitoring progress
                has_video = settings['video_enabled']
                has_audio = settings['audio_enabled']
                threading.Thread(
                    target=self._monitor_youtube_progress,
                    args=(widget, process_id, progress_queue, has_video, has_audio),
                    daemon=True
                ).start()
                
            except RuntimeError as e:
                if "Maximum number of processes" in str(e):
                    self.pending_downloads.append((widget_id, url, settings))
                    widget.set_status("Waiting for available slot...")
                    logger.debug(f"Queued download for later: {url}")
                    self._update_download_counts()
                    return
                raise
                
        except Exception as e:
            logger.error(f"Failed to start download: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Failed to start download: {str(e)}")
            
    def _monitor_youtube_progress(
        self,
        widget: DownloadWidget,
        process_id: str,
        progress_queue: mp.Queue,
        has_video: bool,
        has_audio: bool
    ):
        """Monitor progress of YouTube download"""
        try:
            # Show appropriate progress bars
            if has_audio:
                widget.show_audio_progress()  # Show audio progress if downloading audio
            if has_video:
                widget.show_video_progress()  # Show video progress if downloading video
            is_muxing = False  # Track if we're in muxing phase
            widget.set_status("Starting download...")  # Initial status - yellow
            while True:
                try:
                    progress = progress_queue.get(timeout=0.1)
                    if progress['type'] == 'title':
                        widget.update_title(progress['title'])
                    elif progress['type'] == 'video_progress':
                        data = progress.get('data', {})
                        widget.update_video_progress(
                            data.get('progress', 0),
                            data.get('speed', '0MB/s'),
                            data.get('downloaded', '0MB'),
                            data.get('total', '0MB')
                        )
                    elif progress['type'] == 'audio_progress':
                        data = progress.get('data', {})
                        widget.update_audio_progress(
                            data.get('progress', 0),
                            data.get('speed', '0MB/s'),
                            data.get('downloaded', '0MB'),
                            data.get('total', '0MB')
                        )
                    elif progress['type'] == 'muxing_progress':
                        is_muxing = True  # Set muxing flag
                        data = progress.get('data', {})
                        widget.show_muxing_progress()
                        widget.update_muxing_progress(
                            data.get('progress', 0),
                            data.get('status', 'Muxing...')
                        )
                        widget.set_status("Muxing video and audio...")  # Update status during muxing
                    elif progress['type'] == 'status':
                        widget.set_status(progress['message'])
                    elif progress['type'] == 'error':
                        widget.set_status(f"Error: {progress['error']}")
                        widget.is_completed = True
                        widget.is_cancelled = True
                        self._clear_download(process_id)
                        break
                    elif progress['type'] == 'cancelled':
                        widget.set_status("Download cancelled")
                        widget.is_completed = True
                        widget.is_cancelled = True
                        self._clear_download(process_id)
                        break
                    elif progress['type'] == 'complete':
                        if is_muxing:
                            widget.set_status("Finished!")  # Update status after muxing
                        else:
                            widget.set_status(progress.get('message', 'Finished!'))  # Use message if provided
                        
                        # Set the downloaded file path if provided
                        if 'file_path' in progress:
                            # Support multiple files (video+audio, non-muxed)
                            if isinstance(progress['file_path'], list):
                                widget.set_downloaded_path(progress['file_path'])
                            else:
                                widget.set_downloaded_path(progress['file_path'])
                        
                        widget.is_completed = True
                        widget.is_cancelled = True
                        self._clear_download(process_id)
                        break
                except queue.Empty:
                    if not self.process_pool.is_process_running(process_id):
                        if not is_muxing:  # Only show failure if not in muxing phase
                            widget.set_status("Download failed")
                            widget.is_completed = True
                            widget.is_cancelled = True
                            self._clear_download(process_id)
                            break
        except Exception as e:
            logger.error(f"Error monitoring progress: {str(e)}", exc_info=True)
            widget.set_status(f"Error: {str(e)}")
            widget.is_completed = True
            widget.is_cancelled = True
            self._clear_download(process_id)
            
    def _monitor_download_progress(
        self,
        widget: DownloadWidget,
        process_id: str,
        progress_queue: mp.Queue
    ):
        """Monitor progress of file download"""
        try:
            widget.show_file_progress()
            widget.set_status("Starting download...")  # Initial status - yellow
            last_update_time = 0
            MIN_UPDATE_INTERVAL = 0.05
            while process_id in self.active_downloads:
                try:
                    progress = progress_queue.get(timeout=0.5)
                    current_time = time.time()
                    if progress['type'] == 'progress':
                        if current_time - last_update_time >= MIN_UPDATE_INTERVAL:
                            data = progress.get('data', {})
                            widget.update_file_progress(
                                data.get('progress', 0),
                                data.get('speed', '0MB/s'),
                                data.get('downloaded', '0MB'),
                                data.get('total', '0MB')
                            )
                            last_update_time = current_time
                    elif progress['type'] == 'status':
                        widget.set_status(progress.get('message', ''))
                    elif progress['type'] == 'title':
                        widget.update_title(progress['title'])
                    elif progress['type'] == 'error':
                        widget.set_status(f"Error: {progress['error']}")
                        widget.is_completed = True
                        widget.is_cancelled = True
                        widget.cancel_btn.configure(text="Clear")
                        self._clear_download(process_id)
                        break
                    elif progress['type'] == 'cancelled':
                        widget.set_status("Download cancelled")
                        widget.is_completed = True
                        widget.is_cancelled = True
                        widget.cancel_btn.configure(text="Clear")
                        self._clear_download(process_id)
                        break
                    elif progress['type'] == 'complete':
                        widget.set_status("Download complete")
                        
                        # Set the downloaded file path if provided
                        if 'file_path' in progress:
                            widget.set_downloaded_path(progress['file_path'])
                        
                        widget.is_completed = True
                        widget.is_cancelled = True
                        widget.cancel_btn.configure(text="Clear")
                        self._clear_download(process_id)
                        break
                except queue.Empty:
                    if not self.process_pool.is_process_running(process_id):
                        widget.set_status("Download failed")
                        widget.is_completed = True
                        widget.is_cancelled = True
                        widget.cancel_btn.configure(text="Clear")
                        self._clear_download(process_id)
                        break
        except Exception as e:
            logger.error(f"Error monitoring progress: {str(e)}", exc_info=True)
            widget.set_status(f"Error: {str(e)}")
            widget.is_completed = True
            widget.is_cancelled = True
            widget.cancel_btn.configure(text="Clear")
            self._clear_download(process_id)
            
    def _clear_download(self, process_id: str):
        """Remove a download from active downloads"""
        if process_id in self.active_downloads:
            self.active_downloads.remove(process_id)
            self._check_pending_downloads()
            self._update_download_counts()
            
    def _check_pending_downloads(self):
        """Check if there are pending downloads that can be started"""
        # Clean up completed processes first
        self.process_pool.cleanup_completed()
        
        # Now check how many active processes we have
        active_processes = len([p for p in self.process_pool.processes.values() if p.is_alive()])

        while active_processes < self.process_pool.max_processes and self.pending_downloads:
            widget_id, url, settings = self.pending_downloads.pop(0)
            try:
                if is_youtube_url(url):
                    self._download_youtube(widget_id, url, settings)
                else:
                    self._download_file(widget_id, url, settings)
            except Exception as e:
                logger.error(f"Error starting pending download {url}: {str(e)}", exc_info=True)
                messagebox.showerror("Error", f"Failed to start download: {str(e)}")
            
            # Recalculate active processes after starting a download
            active_processes = len([p for p in self.process_pool.processes.values() if p.is_alive()])

        # Schedule next check if there are still pending downloads
        if self.pending_downloads:
            self.root.after(1000, self._check_pending_downloads)
        self._update_download_counts()
            
    def _process_next_url(self, urls, settings, remaining_urls):
        """Process next URL in the list asynchronously"""
        if not urls:
            # All URLs processed, update text box with remaining URLs
            self.url_text.delete("1.0", "end")
            if remaining_urls:
                for url in remaining_urls:
                    self.url_text.insert("end", url + "\n")
            return

        # Process URLs in batches of 5 to avoid overwhelming the system
        batch_size = 5
        current_batch = urls[:batch_size]
        remaining_batch = urls[batch_size:]

        # Update text box to remove the processed URLs
        self.url_text.delete("1.0", "end")
        # Add remaining unprocessed URLs
        for remaining_url in remaining_batch:
            self.url_text.insert("end", remaining_url + "\n")
        # Add previously invalid URLs
        for invalid_url in remaining_urls:
            self.url_text.insert("end", invalid_url + "\n")

        # Create a queue to track validation results
        validation_queue = queue.Queue()
        validation_threads = []

        def validate_url(url_to_validate):
            """Validate a single URL"""
            if '.' not in url_to_validate or not all(p.strip() for p in url_to_validate.split('.')):
                validation_queue.put((url_to_validate, False))
                return

            try:
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                })
                url_to_check = url_to_validate if url_to_validate.startswith(('http://', 'https://')) else f'https://{url_to_validate}'
                response = session.head(url_to_check, timeout=5, allow_redirects=True)
                response.raise_for_status()
                validation_queue.put((url_to_validate, True))
            except Exception as e:
                logger.debug(f"Invalid URL {url_to_validate}: {str(e)}")
                validation_queue.put((url_to_validate, False))

        # Start validation threads for the batch
        for url in current_batch:
            thread = threading.Thread(target=validate_url, args=(url,), daemon=True)
            validation_threads.append(thread)
            thread.start()

        def check_validation_results():
            """Check validation results and start downloads"""
            completed = 0
            new_remaining_urls = []

            # Check how many validations are complete
            while not validation_queue.empty():
                url, is_valid = validation_queue.get()
                completed += 1
                if is_valid:
                    # URL is valid, start or queue download
                    self._start_single_download(url, settings.copy())
                else:
                    new_remaining_urls.append(url)

            if completed < len(current_batch):
                # Not all validations are complete, check again after a short delay
                self.root.after(100, check_validation_results)
            else:
                # All validations in this batch are complete, process next batch
                remaining_urls.extend(new_remaining_urls)
                self.root.after(1, lambda: self._process_next_url(remaining_batch, settings, remaining_urls))

        # Start checking validation results
        self.root.after(100, check_validation_results)
            
    def _start_single_download(self, url: str, settings: dict):
        """Start or queue a single download"""
        import mimetypes
        ext = os.path.splitext(url.split('?')[0])[1].lower()
        mime, _ = mimetypes.guess_type(url)
        if is_youtube_url(url):
            if settings['audio_enabled'] and not settings['video_enabled']:
                file_type = 'audio'
            elif settings['video_enabled'] and not settings['audio_enabled']:
                file_type = 'video'
            else:
                file_type = 'video'  # Default to video for video+audio downloads
        elif mime and mime.startswith('video'):
            file_type = 'video'
        elif mime and mime.startswith('audio'):
            file_type = 'audio'
        else:
            file_type = 'file'
        title = get_filename_from_url(url)
        if is_youtube_url(url):
            if settings['audio_enabled'] and not settings['video_enabled']:
                format_info = "Audio"
                format_info += f" ({settings['audio_quality']})"
            elif settings['video_enabled'] and not settings['audio_enabled']:
                format_info = "Video"
                format_info += f" ({settings['video_quality']})"
            else:
                format_info = "Video"
                format_info += f" ({settings['video_quality']}, {settings['audio_quality']})"
            title = f"{title} - {format_info}"
        widget_id = self._create_download_widget(title, url, file_type=file_type)
        if len(self.active_downloads) < self.process_pool.max_processes:
            if is_youtube_url(url):
                self._download_youtube(widget_id, url, settings)
            else:
                self._download_file(widget_id, url, settings)
        else:
            self.pending_downloads.append((widget_id, url, settings))
            widget = self.downloads[widget_id]
            widget.set_status("Waiting for available slot...")
            widget.hide_progress_frame()
            self.root.after(1000, self._check_pending_downloads)
        self._update_download_counts()
            
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
                'audio_enabled': self.settings_panel.audio_enabled.get(),
                'video_enabled': self.settings_panel.video_enabled.get(),
                'muxing_enabled': self.settings_panel.muxing_enabled.get()
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
        self._check_pending_downloads()  # Check if we can start any queued downloads
        
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
            
            # Get URLs from text field
            urls = [url.strip() for url in self.url_text.get("1.0", "end").split("\n") if url.strip()]
            
            # Update settings panel checkbox visibility based on URL content
            if hasattr(self, 'settings_panel'):
                self.settings_panel.update_checkbox_visibility(urls)
            
            # Check content for playlist URLs
            has_playlists = any("list=" in url for url in urls)
            
            # Update button text
            self.download_btn.configure(
                text="Extract Playlists" if has_playlists else "Start Downloads",
                fg_color="#d29922" if has_playlists else "#2ea043",  # Warm yellow for playlists, GitHub-style green for downloads
                hover_color="#bf8700" if has_playlists else "#2c974b",  # Darker yellow for hover on playlists, darker green for hover on downloads
                text_color="black",
                font=("", 13, "bold")
            )
        except Exception as e:
            logger.error(f"Error updating button text: {str(e)}", exc_info=True)
            
    def _cancel_queued_downloads(self):
        """Cancel all queued downloads"""
        # Get list of queued downloads
        queued_widgets = []
        for widget_id, widget in self.downloads.items():
            if not widget.process_id:  # No process ID means it's queued
                queued_widgets.append(widget_id)
                
        # Cancel each queued download
        for widget_id in queued_widgets:
            widget = self.downloads[widget_id]
            widget.is_cancelled = True
            widget.set_status("Download cancelled")
            widget.cancel_btn.configure(text="Clear")
            
        # Clear the pending URLs list
        self.pending_downloads.clear()
        self._update_download_counts()
        
    def _cancel_all_downloads(self):
        """Cancel all downloads (both queued and active)"""
        # Show confirmation dialog
        if not messagebox.askyesno(
            "Cancel All Downloads",
            "Are you sure you want to cancel all downloads?\nThis will stop both queued and active downloads."
        ):
            return

        # Cancel queued downloads first
        self.pending_downloads.clear()
        
        # Update all download widgets
        for widget_id, widget in self.downloads.items():
            if not widget.is_completed:  # Don't modify completed downloads
                widget.is_cancelled = True
                widget.set_status("Download cancelled")
                widget.cancel_btn.configure(text="Clear")
                
                # Cancel the process if it's active
                if hasattr(widget, 'process_id') and widget.process_id:
                    self.process_pool.terminate_process(widget.process_id)
                    self._clear_download(widget.process_id)
                    
    def _update_download_counts(self):
        """Update the queue and active download counts"""
        queue_count = len(self.pending_downloads)
        active_count = len(self.active_downloads)
        
        self.queue_count.configure(text=str(queue_count))
        self.active_count.configure(text=str(active_count))

    def run(self):
        """Start the application"""
        self.root.mainloop()

    def _handle_download_error(self, process_id, error_msg):
        """Handle download error"""
        if process_id in self.active_downloads:
            self.active_downloads.remove(process_id)
            self._process_pending_downloads()
            self._update_download_counts()
        logger.error(f"Download error: {error_msg}")

    def _process_progress_updates(self):
        """Process any progress updates from the progress queue"""
        try:
            while True:  # Process all available updates
                update = self.progress_queue.get_nowait()
                process_id = update.get('process_id')
                if process_id in self.downloads:
                    widget = self.downloads[process_id]
                    
                    if 'error' in update:
                        # Handle error
                        error_msg = str(update['error'])
                        widget.set_status(f"Error: {error_msg}")
                        widget.cancel_btn.configure(text="Clear")
                        self._handle_download_error(process_id, error_msg)
                        self._update_download_counts()
                        
                    elif update.get('status') == 'completed':
                        # Handle completion
                        widget.set_status("Completed")
                        widget.is_completed = True
                        widget.cancel_btn.configure(text="Clear")
                        self._clear_download(process_id)
                        self._update_download_counts()
                        
                    elif 'progress' in update:
                        # Update progress
                        progress = update['progress']
                        if 'video' in progress:
                            widget.show_video_progress()
                            widget.update_video_progress(
                                progress['video'].get('progress', 0),
                                progress['video'].get('speed', '0 KB/s'),
                                progress['video'].get('downloaded', '0 MB'),
                                progress['video'].get('total', '0 MB')
                            )
                        if 'audio' in progress:
                            widget.show_audio_progress()
                            widget.update_audio_progress(
                                progress['audio'].get('progress', 0),
                                progress['audio'].get('speed', '0 KB/s'),
                                progress['audio'].get('downloaded', '0 MB'),
                                progress['audio'].get('total', '0 MB')
                            )
                        if 'muxing' in progress:
                            widget.show_muxing_progress()
                            widget.update_muxing_progress(
                                progress['muxing'].get('progress', 0),
                                progress['muxing'].get('status', 'Muxing...')
                            )
                        # Update single progress bar for regular downloads
                        elif 'progress' in progress:
                            widget.show_video_progress()
                            widget.update_video_progress(
                                progress.get('progress', 0),
                                progress.get('speed', '0 KB/s'),
                                progress.get('downloaded', '0 MB'),
                                progress.get('total', '0 MB')
                            )
                
        except queue.Empty:
            pass  # No more updates to process
        except Exception as e:
            logger.error(f"Error processing progress updates: {str(e)}", exc_info=True)
        finally:
            # Schedule next update
            self.root.after(100, self._process_progress_updates)

    def _check_pending_downloads(self):
        """Check if there are pending downloads that can be started"""
        while (len(self.active_downloads) < self.process_pool.max_processes and 
               self.pending_downloads):
            widget_id, url, settings = self.pending_downloads.pop(0)
            try:
                if is_youtube_url(url):
                    self._download_youtube(widget_id, url, settings)
                else:
                    self._download_file(widget_id, url, settings)
            except Exception as e:
                logger.error(f"Error starting pending download {url}: {str(e)}", exc_info=True)
                messagebox.showerror("Error", f"Failed to start download: {str(e)}")
            
            # Recalculate active processes after starting a download
            active_processes = len([p for p in self.process_pool.processes.values() if p.is_alive()])

        # Update counts after processing pending downloads
        self._update_download_counts()

    def _settings_changed(self, setting_name: str, value: Any):
        """Handle settings changes"""
        if setting_name == "max_concurrent_downloads":
            # Check if we can start any queued downloads with the new limit
            self._check_pending_downloads()
