from typing import Optional, Callable, Dict, Any, Tuple
import os
from pathlib import Path
import subprocess
import yt_dlp
import json
from multiprocessing import Queue, Process
import multiprocessing as mp
import uuid
from utils.exceptions import YouTubeError, FFmpegError, DownloadError
from utils.logger import Logger
import unicodedata
from .utils import ensure_unique_path

logger = Logger.get_instance()

def clean_filename(filename: str) -> str:
    """Clean filename from invalid characters and normalize Unicode characters"""
    # Normalize Unicode characters (NFKD form converts special characters to their ASCII equivalents where possible)
    filename = unicodedata.normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')

    # Characters not allowed in Windows filenames
    invalid_chars = r'<>:"/\|?*'
    # Replace invalid characters with underscore
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # Remove any leading/trailing spaces and dots
    filename = filename.strip('. ')
    # Limit length to avoid potential issues
    return filename[:200]

def get_video_info(url: str) -> Dict[str, Any]:
    """Get video information including available formats"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                'title': clean_filename(info.get('title', '')),
                'duration': info.get('duration', 0),
                'formats': info.get('formats', [])
            }
        except Exception as e:
            raise YouTubeError(f"Failed to get video info: {str(e)}")

def download_video(
    url: str,
    dest_folder: str,
    video_quality: str,
    audio_quality: str,
    audio_only: bool = False,
    video_queue: Any = None,
    audio_queue: Any = None
) -> Tuple[Optional[str], str]:
    """Download video from YouTube"""
    try:
        # Get video info first
        info = get_video_info(url)
        
        # Create unique temporary filenames
        video_temp = None if audio_only else os.path.join(dest_folder, f"video_{uuid.uuid4()}.mp4")
        audio_temp = os.path.join(dest_folder, f"audio_{uuid.uuid4()}.m4a")
        
        # Get target height from video quality
        target_height = int(video_quality.split('p')[0]) if 'p' in video_quality else 0
        
        # Get target audio bitrate
        target_bitrate = {
            "High (opus)": 160,
            "High (m4a)": 128,
            "Medium (opus)": 128,
            "Medium (m4a)": 96,
            "Low (opus)": 96,
            "Low (m4a)": 64
        }.get(audio_quality, 128)  # Default to 128k if not found
        
        # Configure yt-dlp options
        if not audio_only:
            # Download video
            ydl_opts = {
                'format': f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[abr<={target_bitrate}][ext=m4a]',
                'outtmpl': {'video': video_temp, 'audio': audio_temp},
                'progress_hooks': [
                    lambda d: handle_progress(d, video_queue if d['info_dict'].get('vcodec') != 'none' else audio_queue)
                ],
                'quiet': True,
                'no_warnings': True
            }
        else:
            # Download audio only
            ydl_opts = {
                'format': f'bestaudio[abr<={target_bitrate}][ext=m4a]',
                'outtmpl': {'audio': audio_temp},
                'progress_hooks': [lambda d: handle_progress(d, audio_queue)],
                'quiet': True,
                'no_warnings': True
            }
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        return video_temp, audio_temp
        
    except Exception as e:
        raise DownloadError(f"Download failed: {str(e)}")

def handle_progress(d: dict, queue: Optional[Queue]):
    """Handle download progress updates"""
    if queue is None:
        return
        
    try:
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0)
            
            if total > 0:
                progress = {
                    'percent': (downloaded / total) * 100,
                    'speed': speed,
                    'total': total,
                    'downloaded': downloaded
                }
                queue.put(progress)
                
    except Exception as e:
        logger.error(f"Error handling progress: {str(e)}")

def mux_files(
    video_path: Optional[str],
    audio_path: str,
    output_path: str,
    progress_queue: Optional[Any] = None
):
    """Mux video and audio files using ffmpeg"""
    try:
        # Update progress
        if progress_queue:
            progress_queue.put({
                'type': 'muxing_progress',
                'data': {'progress': 0, 'status': 'Starting muxing...'}
            })
        
        if video_path:
            # Mux video and audio
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-c', 'copy',
                output_path
            ]
            logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
        else:
            # Audio only, just copy
            cmd = [
                'ffmpeg', '-y',
                '-i', audio_path,
                '-c', 'copy',
                output_path
            ]
            logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
            
        # Run ffmpeg
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Monitor progress
        duration = None
        time_position = 0
        stderr_output = []
        
        while True:
            line = process.stderr.readline()
            if not line:
                break
                
            # Store stderr output for error reporting
            stderr_output.append(line)
            
            # Try to get duration if we don't have it
            if not duration and "Duration:" in line:
                try:
                    duration_str = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = map(float, duration_str.split(":"))
                    duration = h * 3600 + m * 60 + s
                    logger.debug(f"Detected duration: {duration}s")
                except Exception as e:
                    logger.warning(f"Failed to parse duration: {e}")
                    
            # Try to get current position
            if "time=" in line:
                try:
                    time_str = line.split("time=")[1].split()[0].strip()
                    h, m, s = map(float, time_str.split(":"))
                    time_position = h * 3600 + m * 60 + s
                    
                    if duration:
                        progress = (time_position / duration) * 100
                        if progress_queue:
                            progress_queue.put({
                                'type': 'muxing_progress',
                                'data': {
                                    'progress': min(progress, 100),
                                    'status': f'Processing... {progress:.1f}%'
                                }
                            })
                        logger.debug(f"Muxing progress: {progress:.1f}%")
                except Exception as e:
                    logger.warning(f"Failed to parse time position: {e}")
                    
        # Wait for process to finish
        process.wait()
        
        # Check if successful
        if process.returncode == 0:
            if progress_queue:
                progress_queue.put({
                    'type': 'muxing_progress',
                    'data': {'progress': 100, 'status': 'Muxing complete'}
                })
                progress_queue.put({'type': 'complete'})
            # Clean up temporary files
            if video_path:
                os.remove(video_path)
            os.remove(audio_path)
            logger.info("Muxing completed successfully")
        else:
            error = '\n'.join(stderr_output)
            logger.error(f"FFmpeg failed with return code {process.returncode}. Error output:\n{error}")
            raise FFmpegError(f"FFmpeg failed with code {process.returncode}: {error}")
            
    except Exception as e:
        logger.error(f"Muxing failed: {str(e)}", exc_info=True)
        if progress_queue:
            progress_queue.put({
                'type': 'error',
                'error': str(e)
            })
        raise

class YouTubeDownloader:
    # Video format codes mapping
    VIDEO_FORMATS = {
        "2160p (4K)": ["313", "401"],
        "1440p (2K)": ["271", "400"],
        "1080p": ["137", "248", "399"],
        "720p": ["136", "247", "398"],
        "480p": ["135", "244", "397"],
        "360p": ["134", "243", "396"],
        "240p": ["133", "242", "395"],
        "144p": ["160", "278", "394"]
    }
    
    # Audio format codes mapping
    AUDIO_FORMATS = {
        "High (opus)": ["251"],
        "High (m4a)": ["140"],
        "Medium (opus)": ["250"],
        "Medium (m4a)": ["139"],
        "Low (opus)": ["249"],
        "Low (m4a)": ["599"]
    }
    
    get_video_info = staticmethod(get_video_info)
    download_video = staticmethod(download_video)
    mux_files = staticmethod(mux_files)
    clean_filename = staticmethod(clean_filename)
    
    @staticmethod
    def get_playlist_urls(url: str) -> list[str]:
        """Get all video URLs from a playlist"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'flat_playlist': True,
            'ignoreerrors': True,  # Skip unavailable videos
            'no_color': True
        }
        
        logger.debug(f"Getting playlist URLs from: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                logger.debug(f"Playlist info: {info.keys()}")
                
                if 'entries' in info:
                    # This is a playlist, return all video URLs
                    urls = []
                    for entry in info['entries']:
                        logger.debug(f"Entry: {entry.keys()}")
                        if entry and 'id' in entry:  # Skip None entries
                            video_url = f"https://www.youtube.com/watch?v={entry['id']}"
                            urls.append(video_url)
                    
                    logger.debug(f"Found {len(urls)} videos in playlist")
                    return urls
                else:
                    # Not a playlist, return empty list
                    logger.debug("No entries found in playlist info")
                    return []
                    
            except Exception as e:
                logger.error(f"Failed to get playlist info: {str(e)}", exc_info=True)
                raise Exception(f"Failed to get playlist info: {str(e)}")
    
    @staticmethod
    def stream_progress_hook(d: dict, stream_type: str, progress_queue: Any):
        """Progress hook for stream downloads"""
        if d['status'] == 'downloading':
            try:
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                speed = d.get('speed', 0)
                
                if total and downloaded:
                    progress = (downloaded / total) * 100
                    speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else ""
                    downloaded_str = f"{downloaded/1024/1024:.1f} MB"
                    total_str = f"{total/1024/1024:.1f} MB"
                    
                    progress_queue.put({
                        'type': f'{stream_type}_progress',
                        'data': {
                            'progress': progress,
                            'speed': speed_str,
                            'downloaded': downloaded_str,
                            'total': total_str
                        }
                    })
            except Exception as e:
                logger.error(f"Error in progress hook: {str(e)}", exc_info=True)
                
    @staticmethod
    def download_stream(url: str, options: dict, stream_type: str, progress_queue: Any):
        """Download a single stream (video or audio)"""
        try:
            logger.info(f"Starting {stream_type} download for {url}")
            logger.debug(f"{stream_type.title()} download options: {options}")
            
            options['progress_hooks'] = [
                lambda d: YouTubeDownloader.stream_progress_hook(d, stream_type, progress_queue)
            ]
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
                
            logger.info(f"Finished {stream_type} download")
            
        except Exception as e:
            error_msg = f"Failed to download {stream_type}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            progress_queue.put({
                'type': 'error',
                'error': error_msg
            })
            raise DownloadError(error_msg)
            
    @staticmethod
    def download_process(
        url: str,
        dest_folder: str,
        video_quality: str,
        audio_quality: str,
        audio_only: bool,
        progress_queue: Any
    ):
        """Standalone process for downloading YouTube videos"""
        try:
            logger.info(f"Starting YouTube download process for {url}")
            logger.debug(f"Settings - Quality: {video_quality}, Audio: {audio_quality}, Audio Only: {audio_only}")
            
            # Get video info first
            logger.debug("Fetching video info...")
            info = get_video_info(url)
            title = info.get('title', 'Unknown')
            clean_title = clean_filename(title)  # Clean the title before logging
            logger.info(f"Video title: {clean_title}")
            
            # Create unique temporary filenames
            video_temp = None if audio_only else os.path.join(dest_folder, f"video_{uuid.uuid4()}.mp4")
            audio_temp = os.path.join(dest_folder, f"audio_{uuid.uuid4()}.m4a")
            logger.debug(f"Temp files - Video: {video_temp}, Audio: {audio_temp}")
            
            # Get target height from video quality
            target_height = int(video_quality.split('p')[0]) if 'p' in video_quality else 0
            logger.debug(f"Target height: {target_height}p")
            
            # Get target audio bitrate
            target_bitrate = {
                "High (opus)": 160,
                "High (m4a)": 128,
                "Medium (opus)": 128,
                "Medium (m4a)": 96,
                "Low (opus)": 96,
                "Low (m4a)": 64
            }.get(audio_quality, 128)
            logger.debug(f"Target audio bitrate: {target_bitrate}k")
            
            # Configure audio download options
            audio_opts = {
                'format': f'bestaudio[abr<={target_bitrate}][ext=m4a]',
                'outtmpl': {'default': audio_temp},
                'quiet': True,
                'no_warnings': True
            }
            
            # Configure video download options
            video_opts = None
            if not audio_only:
                video_opts = {
                    'format': f'bestvideo[height<={target_height}][ext=mp4]',
                    'outtmpl': {'default': video_temp},
                    'quiet': True,
                    'no_warnings': True
                }
            
            # Start downloads in parallel
            processes = []
            
            # Start audio download
            audio_process = Process(
                target=YouTubeDownloader.download_stream,
                args=(url, audio_opts, 'audio', progress_queue)
            )
            audio_process.start()
            processes.append(audio_process)
            
            # Start video download if needed
            if video_opts:
                video_process = Process(
                    target=YouTubeDownloader.download_stream,
                    args=(url, video_opts, 'video', progress_queue)
                )
                video_process.start()
                processes.append(video_process)
            
            # Wait for all downloads to complete
            for p in processes:
                p.join()
                if p.exitcode != 0:
                    raise DownloadError("Download process failed")
            
            # Merge files if needed
            base_output_path = Path(dest_folder) / f"{clean_filename(info['title'])}.mp4"
            output_path = ensure_unique_path(base_output_path)
            if not audio_only:
                logger.info(f"Merging files to: {output_path}")
                YouTubeDownloader.mux_files(video_temp, audio_temp, str(output_path), progress_queue)
            else:
                # For audio only, just rename the temp file
                os.rename(audio_temp, str(output_path))
                progress_queue.put({
                    'type': 'complete'
                })
            
        except Exception as e:
            error_msg = f"Download process failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            progress_queue.put({
                'type': 'error',
                'error': error_msg
            })
            raise YouTubeError(error_msg)
            
    @staticmethod
    def monitor_progress(progress_queue: Any, video_queue: Any = None, audio_queue: Any = None) -> None:
        """Monitor download progress and forward to main queue"""
        try:
            # Check video progress
            if video_queue and not video_queue.empty():
                progress = video_queue.get_nowait()
                progress_queue.put({
                    'type': 'video_progress',
                    'data': progress
                })
                
            # Check audio progress
            if audio_queue and not audio_queue.empty():
                progress = audio_queue.get_nowait()
                progress_queue.put({
                    'type': 'audio_progress',
                    'data': progress
                })
                
        except Exception as e:
            progress_queue.put({
                'type': 'error',
                'error': str(e)
            })
