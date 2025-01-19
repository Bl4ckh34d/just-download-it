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

from utils.exceptions import DownloadError
from utils.logger import Logger

logger = Logger.get_logger(__name__)

class FileDownloader:
    CHUNK_SIZE = 8192  # 8KB chunks
    
    @staticmethod
    def download(url: str, dest_folder: str, progress_queue: Any) -> None:
        """Download a file from a URL to the destination folder"""
        try:
            logger.info(f"Starting download from {url}")
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
            
            # Start download
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
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed: {error_msg}", exc_info=True)
            progress_queue.put({'type': 'error', 'error': error_msg})
            raise DownloadError(error_msg)
            
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
