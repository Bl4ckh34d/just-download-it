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

from utils.exceptions import DownloadError
from utils.logger import Logger

logger = Logger.get_logger(__name__)

class FileDownloader:
    CHUNK_SIZE = 8192  # 8KB chunks
    MIN_CHUNK_SIZE = 1024 * 1024  # 1MB minimum chunk size for parallel downloads
    
    @staticmethod
    def download(url: str, dest_folder: str, progress_queue: Any, thread_count: int = 4) -> None:
        """Download a file from a URL to the destination folder using multiple threads"""
        try:
            logger.info(f"Starting download from {url} using {thread_count} threads")
            logger.debug(f"Destination folder: {dest_folder}")
            
            # Create destination folder if it doesn't exist
            os.makedirs(dest_folder, exist_ok=True)
            
            # Get filename from URL and create Path objects
            filename = url.split('/')[-1]
            dest_path = Path(dest_folder) / filename
            logger.debug(f"Destination path: {dest_path}")
            
            # Get browser cookies and convert to requests format
            cookies = FileDownloader._get_cookies(url)
            logger.debug(f"Got {len(cookies)} cookies for {url}")
            
            # Setup session with headers
            session = requests.Session()
            session.cookies.update(cookies)
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            # Send HEAD request to get content length
            response = session.head(url, allow_redirects=True)
            total_size = int(response.headers.get('content-length', 0))
            
            if total_size == 0:
                # If size unknown or too small, fall back to single thread download
                logger.warning("File size unknown or too small, falling back to single thread download")
                FileDownloader._single_thread_download(session, url, dest_path, total_size, progress_queue)
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
            
            def download_chunk(chunk_info):
                chunk_start, chunk_end = chunks[chunk_info[0]]
                temp_file = chunk_info[1]
                
                headers = {'Range': f'bytes={chunk_start}-{chunk_end}'}
                response = session.get(url, headers=headers, stream=True)
                
                with open(temp_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=FileDownloader.CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            with lock:
                                downloaded.value += len(chunk)
                                elapsed = time.time() - start_time
                                speed = downloaded.value / elapsed if elapsed > 0 else 0
                                
                                # Format values for progress
                                speed_str = f"{speed/1024/1024:.1f}MB/s"
                                downloaded_str = f"{downloaded.value/1024/1024:.1f}MB"
                                total_str = f"{total_size/1024/1024:.1f}MB"
                                
                                progress = {
                                    'type': 'progress',
                                    'data': {
                                        'progress': (downloaded.value / total_size) * 100,
                                        'speed': speed_str,
                                        'downloaded': downloaded_str,
                                        'total': total_str
                                    }
                                }
                                progress_queue.put(progress)
            
            # Download chunks in parallel
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                executor.map(download_chunk, enumerate(temp_files))
            
            # Combine all chunks
            with open(dest_path, 'wb') as dest:
                for temp_file in temp_files:
                    with open(temp_file, 'rb') as src:
                        dest.write(src.read())
                    # Clean up temp file
                    temp_file.unlink()
            
            logger.info("Download completed successfully")
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
                              total_size: int, progress_queue: Any):
        """Fallback method for single-threaded download"""
        response = session.get(url, stream=True)
        response.raise_for_status()
        
        with open(dest_path, 'wb') as f:
            downloaded = 0
            start_time = time.time()
            
            for chunk in response.iter_content(chunk_size=FileDownloader.CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        # Calculate speed and progress
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        
                        # Format values
                        speed_str = f"{speed/1024/1024:.1f}MB/s"
                        downloaded_str = f"{downloaded/1024/1024:.1f}MB"
                        total_str = f"{total_size/1024/1024:.1f}MB"
                        
                        progress = {
                            'type': 'progress',
                            'data': {
                                'progress': (downloaded / total_size) * 100,
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
            progress_queue.put({'type': 'complete'})
            
    @staticmethod
    def _get_cookies(url: str) -> dict:
        """Get cookies from installed browsers"""
        cookies = {}
        try:
            logger.debug("Attempting to get Chrome cookies")
            try:
                chrome_cookies = browsercookie.chrome()
                for cookie in chrome_cookies:
                    if cookie.domain in url:
                        cookies[cookie.name] = cookie.value
                logger.debug(f"Got {len(cookies)} Chrome cookies")
            except Exception as e:
                logger.warning(f"Failed to get Chrome cookies: {e}")
                
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
                logger.warning(f"Failed to get Firefox cookies: {e}")
                
        except Exception as e:
            logger.warning(f"Error getting browser cookies: {e}")
            
        return cookies
        
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes into human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
