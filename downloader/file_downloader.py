from typing import Optional
import os
from pathlib import Path
import requests
import browser_cookie3 as browsercookie
import logging
import traceback
import multiprocessing as mp
import time
from typing import Any
import threading
from concurrent.futures import ThreadPoolExecutor
import math

from utils import utils
from utils.exceptions import DownloadError, BrowserCookieError
from utils.logger import Logger
from utils.utils_downloader import format_size

logger = Logger.get_logger(__name__)

class FileDownloader:
    CHUNK_SIZE = 8192  # 8KB chunks
    MIN_CHUNK_SIZE = 1024 * 1024  # 1MB minimum chunk size for parallel downloads
    
    @staticmethod
    def download(url: str, dest_folder: str, progress_queue: Any, thread_count: int = 4, cancel_event: mp.Event = None) -> None:
        """Download a file from a URL to the destination folder using multiple threads"""
        try:
            logger.info(f"Starting download from {url}")
            progress_queue.put({'type': 'status', 'message': 'Initializing download...'})
            
            progress_queue.put({'type': 'status', 'message': 'Resolving filename and preparing download...'})
            # Create destination folder if it doesn't exist
            os.makedirs(dest_folder, exist_ok=True)
            
            # Get filename from URL and create Path objects
            filename = url.split('/')[-1]
            dest_path = Path(dest_folder) / filename
            logger.debug(f"Destination path: {dest_path}")
            
            progress_queue.put({'type': 'status', 'message': 'Connecting to server...'})
            # Create session with browser cookies
            session = requests.Session()
            try:
                cookies = FileDownloader._get_cookies(url)
                if cookies:
                    session.cookies.update(cookies)
                    logger.debug("Using browser cookies for download")
            except BrowserCookieError as e:
                # Log the error but continue without cookies
                logger.debug(f"Continuing download without browser cookies: {e}")
                progress_queue.put({
                    'type': 'status',
                    'message': 'Browser cookies not available, continuing without them...'
                })
            
            # Setup session with headers
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            progress_queue.put({'type': 'status', 'message': 'Checking file metadata...'})
            # Send HEAD request to get content length
            response = session.head(url, allow_redirects=True)
            total_size = int(response.headers.get('content-length', 0))
            
            if total_size == 0:
                # If size unknown or too small, fall back to single thread download
                logger.warning("File size unknown or too small, falling back to single thread download")
                progress_queue.put({'type': 'status', 'message': 'File size unknown, downloading as single stream...'})
                FileDownloader._single_thread_download(session, url, dest_path, total_size, progress_queue, cancel_event)
                return
                
            # Calculate chunk size based on file size and thread count
            chunk_size = max(FileDownloader.MIN_CHUNK_SIZE, math.ceil(total_size / thread_count))
            chunks = [(start, min(start + chunk_size - 1, total_size))
                     for start in range(0, total_size, chunk_size)]
            
            # Create temporary files for each chunk
            temp_files = [dest_path.with_suffix(f'.part{i}')
                         for i in range(len(chunks))]
            
            # Shared variables for progress tracking
            downloaded = mp.Value('i', 0)
            lock = threading.Lock()
            start_time = time.time()

            # Notify UI that download is starting
            progress_queue.put({'type': 'status', 'message': f'Starting download with {thread_count} threads...'})

            def download_chunk(chunk_info):
                chunk_start, chunk_end = chunks[chunk_info[0]]
                temp_file = chunk_info[1]
                logger.debug(f"Thread {chunk_info[0]} downloading bytes {chunk_start}-{chunk_end}")
                headers = {'Range': f'bytes={chunk_start}-{chunk_end}'}
                response = session.get(url, headers=headers, stream=True)
                with open(temp_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=FileDownloader.CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            with lock:
                                prev_downloaded = downloaded.value
                                downloaded.value = max(0, min(downloaded.value + len(chunk), total_size))
                                logger.debug(f"Thread {chunk_info[0]} wrote {len(chunk)} bytes, prev_downloaded={prev_downloaded}, new_downloaded={downloaded.value}")
                                if downloaded.value < 0 or downloaded.value > total_size:
                                    logger.warning(f"[BUG] downloaded.value out of bounds: {downloaded.value} (total_size={total_size})")
                                elapsed = time.time() - start_time
                                speed = downloaded.value / elapsed if elapsed > 0 else 0
                                speed_str = f"{speed/1024/1024:.1f}MB/s"
                                downloaded_str = f"{max(0, min(downloaded.value, total_size))/1024/1024:.1f}MB"
                                total_str = f"{total_size/1024/1024:.1f}MB"
                                progress = {
                                    'type': 'progress',
                                    'data': {
                                        'progress': (max(0, min(downloaded.value, total_size)) / total_size) * 100 if total_size > 0 else 0,
                                        'speed': speed_str,
                                        'downloaded': downloaded_str,
                                        'total': total_str
                                    }
                                }
                                progress_queue.put(progress)
                                if cancel_event and cancel_event.is_set():
                                    f.close()
                                    temp_file.unlink()
                                    return
                            
            progress_queue.put({'type': 'status', 'message': 'Downloading...'})
            # Download chunks in parallel
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                executor.map(download_chunk, enumerate(temp_files))
            
            progress_queue.put({'type': 'status', 'message': 'Combining downloaded chunks...'})
            # Combine all chunks
            with open(dest_path, 'wb') as dest:
                for temp_file in temp_files:
                    if temp_file.exists():
                        with open(temp_file, 'rb') as src:
                            dest.write(src.read())
                        # Clean up temp file
                        temp_file.unlink()
            
            logger.info("Download completed successfully")
            progress_queue.put({'type': 'status', 'message': 'Finalizing download...'})
            progress_queue.put({'type': 'complete'})
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed: {error_msg}", exc_info=True)
            progress_queue.put({'type': 'error', 'error': error_msg})
            # Clean up any temporary files
            for temp_file in temp_files:
                if temp_file.exists():
                    temp_file.unlink()
            raise DownloadError(error_msg)
    
    @staticmethod
    def _single_thread_download(session: requests.Session, url: str, dest_path: Path,
                              total_size: int, progress_queue: Any, cancel_event: mp.Event = None):
        """Fallback method for single-threaded download"""
        progress_queue.put({'type': 'status', 'message': 'Connecting and starting single-threaded download...'})
        response = session.get(url, stream=True)
        response.raise_for_status()
        
        with open(dest_path, 'wb') as f:
            downloaded = 0
            start_time = time.time()
            
            for chunk in response.iter_content(chunk_size=FileDownloader.CHUNK_SIZE):
                if cancel_event and cancel_event.is_set():
                    f.close()
                    os.remove(dest_path)  # Clean up partial file
                    progress_queue.put({
                        'type': 'cancelled',
                        'message': 'Download cancelled'
                    })
                    return
                
                if chunk:
                    f.write(chunk)
                    downloaded = max(0, min(downloaded + len(chunk), total_size))
                    if total_size > 0:
                        # Calculate speed and progress
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        # Format values
                        speed_str = f"{speed/1024/1024:.1f}MB/s"
                        downloaded_str = f"{max(0, min(downloaded, total_size))/1024/1024:.1f}MB"
                        total_str = f"{total_size/1024/1024:.1f}MB"
                        progress = {
                            'type': 'progress',
                            'data': {
                                'progress': (max(0, min(downloaded, total_size)) / total_size) * 100 if total_size > 0 else 0,
                                'speed': speed_str,
                                'downloaded': downloaded_str,
                                'total': total_str
                            }
                        }
                        progress_queue.put(progress)
                        # Only log every 5% to reduce spam
                        if int(progress['data']['progress']) % 5 == 0:
                            logger.debug(
                                f"Download progress: {progress['data']['progress']:.1f}% "
                                f"({downloaded_str}/{total_str}) "
                                f"@ {speed_str}"
                            )
            
            logger.info("Download completed successfully")
            progress_queue.put({'type': 'status', 'message': 'Finalizing download...'})
            progress_queue.put({'type': 'complete'})
            
    @staticmethod
    def _get_cookies(url: str) -> dict:
        """Get cookies from installed browsers"""
        cookies = {}
        chrome_error = None
        firefox_error = None

        try:
            logger.debug("Attempting to get Chrome cookies")
            try:
                chrome_cookies = browsercookie.chrome()
                for cookie in chrome_cookies:
                    if cookie.domain in url:
                        cookies[cookie.name] = cookie.value
                logger.debug(f"Got {len(cookies)} Chrome cookies")
            except Exception as e:
                chrome_error = str(e)
                logger.debug(f"Failed to get Chrome cookies: {e}")
                
            logger.debug("Attempting to get Firefox cookies")
            try:
                firefox_cookies = browsercookie.firefox()
                firefox_count = 0
                for cookie in firefox_cookies:
                    if cookie.domain in url:
                        cookies[cookie.name] = cookie.value
                        firefox_count += 1
                logger.debug(f"Got {firefox_count} Firefox cookies")
            except Exception as e:
                firefox_error = str(e)
                logger.debug(f"Failed to get Firefox cookies: {e}")

            if chrome_error and firefox_error:
                raise BrowserCookieError(
                    f"Failed to get cookies from any browser.\n"
                    f"Chrome error: {chrome_error}\n"
                    f"Firefox error: {firefox_error}"
                )
            
            return cookies
        except BrowserCookieError:
            # Re-raise BrowserCookieError as it's already our custom exception
            raise
        except Exception as e:
            # Wrap any other unexpected errors
            raise BrowserCookieError(f"Unexpected error getting browser cookies: {str(e)}")
        
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes into human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
