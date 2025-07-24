from typing import Optional, Callable, Dict, Any, Tuple
import os
from pathlib import Path
import subprocess
import yt_dlp
import json
from multiprocessing import Queue, Process, Event
import multiprocessing as mp
import uuid
from utils.exceptions import YouTubeError, FFmpegError, DownloadError
from utils.logger import Logger
import unicodedata
from utils import ensure_unique_path

logger = Logger.get_logger(__name__)

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
            logger.error(f"Failed to get video info: {str(e)}", exc_info=True)
            raise YouTubeError(f"Failed to get video info: {str(e)}")

def find_best_matching_resolution(formats: list, target_height: int) -> int:
    """
    Find the best matching resolution from available formats, considering both higher and lower resolutions.
    Returns the height of the best matching format.
    """
    # Extract all available heights from formats
    available_heights = set()
    for fmt in formats:
        if fmt.get('height') and fmt.get('vcodec') != 'none':
            available_heights.add(fmt['height'])
    
    if not available_heights:
        raise YouTubeError("No video formats found")
    
    available_heights = sorted(list(available_heights))
    
    # If target is lower than minimum available, return minimum
    if target_height <= available_heights[0]:
        return available_heights[0]
    
    # If target is higher than maximum available, return maximum
    if target_height >= available_heights[-1]:
        return available_heights[-1]
    
    # Find the closest resolution using alternating higher/lower check
    lower_idx = 0
    higher_idx = 0
    
    # Find the first height that's higher than target
    for i, height in enumerate(available_heights):
        if height > target_height:
            higher_idx = i
            lower_idx = i - 1
            break
    
    while lower_idx >= 0 or higher_idx < len(available_heights):
        # Check lower resolution
        if lower_idx >= 0:
            lower_diff = target_height - available_heights[lower_idx]
            lower_match = available_heights[lower_idx]
        else:
            lower_diff = float('inf')
            
        # Check higher resolution
        if higher_idx < len(available_heights):
            higher_diff = available_heights[higher_idx] - target_height
            higher_match = available_heights[higher_idx]
        else:
            higher_diff = float('inf')
            
        # Return the closest match
        if lower_diff <= higher_diff:
            return lower_match
        else:
            return higher_match
    
    # Fallback to the closest available resolution
    return min(available_heights, key=lambda x: abs(x - target_height))

def find_best_matching_audio_quality(formats: list, target_bitrate: int) -> Tuple[int, str]:
    """
    Find the best matching audio quality from available formats.
    Returns a tuple of (bitrate, codec) of the best matching format.
    """
    # Extract all available audio formats with their bitrates
    available_formats = []
    for fmt in formats:
        # Only consider audio formats
        if fmt.get('acodec') != 'none' and fmt.get('abr'):
            available_formats.append({
                'abr': fmt['abr'],  # Average bitrate
                'acodec': fmt['acodec'],
                'ext': fmt.get('ext', '')
            })
    
    if not available_formats:
        raise YouTubeError("No audio formats found")
    
    # Sort formats by bitrate
    available_formats.sort(key=lambda x: x['abr'])
    available_bitrates = [fmt['abr'] for fmt in available_formats]
    
    # If target is lower than minimum available, return minimum
    if target_bitrate <= available_bitrates[0]:
        best_format = available_formats[0]
        logger.info(f"Selected minimum available audio quality: {best_format['abr']}k {best_format['acodec']}")
        return best_format['abr'], best_format['acodec']
    
    # If target is higher than maximum available, return maximum
    if target_bitrate >= available_bitrates[-1]:
        best_format = available_formats[-1]
        logger.info(f"Selected maximum available audio quality: {best_format['abr']}k {best_format['acodec']}")
        return best_format['abr'], best_format['acodec']
    
    # Find the closest bitrate using alternating higher/lower check
    lower_idx = 0
    higher_idx = 0
    
    # Find the first bitrate that's higher than target
    for i, bitrate in enumerate(available_bitrates):
        if bitrate > target_bitrate:
            higher_idx = i
            lower_idx = i - 1
            break
    
    # Check lower quality
    lower_diff = float('inf') if lower_idx < 0 else target_bitrate - available_bitrates[lower_idx]
    # Check higher quality
    higher_diff = float('inf') if higher_idx >= len(available_bitrates) else available_bitrates[higher_idx] - target_bitrate
    
    # Select the closest match
    if lower_diff <= higher_diff and lower_idx >= 0:
        best_format = available_formats[lower_idx]
    else:
        best_format = available_formats[higher_idx]
    
    logger.info(f"Selected audio quality: {best_format['abr']}k {best_format['acodec']} (requested: {target_bitrate}k)")
    return best_format['abr'], best_format['acodec']

def download_video(
    url: str,
    dest_folder: str,
    video_quality: str,
    audio_quality: str,
    audio_only: bool = False,
    video_queue: Any = None,
    audio_queue: Any = None,
    cancel_event: Event = None
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
        
        if not audio_only and target_height > 0:
            # Find best matching resolution
            best_height = find_best_matching_resolution(info['formats'], target_height)
            logger.info(f"Selected resolution: {best_height}p (requested: {target_height}p)")
            target_height = best_height
        
        # Get target audio bitrate from quality setting
        target_bitrate = {
            "High (opus)": 160,
            "High (m4a)": 128,
            "Medium (opus)": 128,
            "Medium (m4a)": 96,
            "Low (opus)": 96,
            "Low (m4a)": 64
        }.get(audio_quality, 128)  # Default to 128k if not found
        
        # Find best matching audio quality
        best_bitrate, best_codec = find_best_matching_audio_quality(info['formats'], target_bitrate)
        
        # Configure yt-dlp options
        if not audio_only:
            # Download video
            ydl_opts = {
                'format': f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[abr<={best_bitrate}][acodec={best_codec}]',
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
                'format': f'bestaudio[abr<={best_bitrate}][acodec={best_codec}]',
                'outtmpl': {'audio': audio_temp},
                'progress_hooks': [lambda d: handle_progress(d, audio_queue)],
                'quiet': True,
                'no_warnings': True
            }
        
        # Create a custom progress hook that checks for cancellation
        def progress_hook(d):
            if cancel_event.is_set():
                raise Exception("Download cancelled")
            handle_progress(d, video_queue if d['info_dict'].get('vcodec') != 'none' else audio_queue)
            
        ydl_opts['progress_hooks'] = [progress_hook]
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        return video_temp, audio_temp
        
    except Exception as e:
        if str(e) == "Download cancelled":
            raise DownloadError("Download cancelled")
        else:
            logger.error(f"Download failed: {str(e)}", exc_info=True)
            raise DownloadError(f"Download failed: {str(e)}")

def handle_progress(d: dict, queue: Optional[Queue]):
    """Handle download progress updates"""
    if queue is None:
        return
    try:
        if d['status'] == 'downloading':
            total = max(0, d.get('total_bytes') or d.get('total_bytes_estimate', 0))
            downloaded = max(0, min(d.get('downloaded_bytes', 0), total))
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
        logger.error(f"Error handling progress: {str(e)}", exc_info=True)

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
    
    @staticmethod
    def mux_files(
        video_path: Optional[str],
        audio_path: str,
        output_path: str,
        progress_queue: Optional[Any] = None,
        cancel_event: Event = None
    ):
        """Mux video and audio files using ffmpeg"""
        try:
            # Check if already cancelled
            if cancel_event and cancel_event.is_set():
                logger.info("Muxing cancelled before starting")
                return
            if progress_queue:
                progress_queue.put({'type': 'status', 'message': 'Starting muxing process...'})
                
            # Get total duration from file before starting
            probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
            total_duration = float(subprocess.check_output(probe_cmd, universal_newlines=True).strip())
                
            # Prepare ffmpeg command
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file if exists
                '-i', audio_path
            ]
            
            if video_path:
                ffmpeg_cmd.extend(['-i', video_path])
                ffmpeg_cmd.extend([
                    '-c:v', 'copy',  # Copy video stream without re-encoding
                    '-c:a', 'copy'   # Copy audio stream without re-encoding
                ])
            else:
                ffmpeg_cmd.extend([
                    '-c:a', 'copy'   # Copy audio stream without re-encoding
                ])
                
            ffmpeg_cmd.append(output_path)
            
            # Start ffmpeg process
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            if progress_queue:
                progress_queue.put({'type': 'status', 'message': 'Muxing in progress...'})
            
            # Monitor process output
            while True:
                # Check for cancellation
                if cancel_event and cancel_event.is_set():
                    logger.info("Muxing cancelled during process")
                    process.terminate()
                    process.wait(timeout=1)  # Wait for process to terminate
                    # Clean up output file if it exists
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    return
                    
                # Read ffmpeg output
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                    
                # Try to parse progress
                if progress_queue and "time=" in line:
                    try:
                        time_str = line.split("time=")[1].split()[0]
                        time_parts = time_str.split(":")
                        seconds = float(time_parts[0]) * 3600 + float(time_parts[1]) * 60 + float(time_parts[2])
                        
                        # Calculate progress percentage
                        progress = (seconds / total_duration) * 100 if total_duration > 0 else 0
                        
                        # Format time values in MB style for consistency
                        current_mb = (seconds / total_duration) * 100 if total_duration > 0 else 0  # Use percentage as MB for visual consistency
                        total_mb = 100  # Total is always 100 since we're showing percentage
                        
                        # Format status message with time and MB values
                        status = f"{current_mb:.1f}MB/{total_mb:.1f}MB"
                        
                        progress_queue.put({
                            'type': 'muxing_progress',
                            'data': {
                                'progress': progress,
                                'status': status,
                                'downloaded': f"{current_mb:.1f}MB",
                                'total': f"{total_mb:.1f}MB"
                            }
                        })
                    except Exception as e:
                        logger.warning(f"Failed to parse time position: {str(e)}")
                        
            # Check process return code
            if process.returncode != 0:
                error_output = process.stderr.read()
                logger.error(f"FFmpeg failed with error: {error_output}", exc_info=True)
                raise FFmpegError(f"FFmpeg failed with error: {error_output}")
            else:
                # Send completion message
                if progress_queue:
                    progress_queue.put({
                        'type': 'status', 'message': 'Finalizing download...'})
                    progress_queue.put({
                        'type': 'complete',
                        'message': 'Finished!'
                    })
                
        except Exception as e:
            logger.error(f"Error during muxing: {str(e)}", exc_info=True)
            # Clean up output file if it exists
            if os.path.exists(output_path):
                os.remove(output_path)
            raise
    
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
                total = max(0, d.get('total_bytes') or d.get('total_bytes_estimate', 0))
                downloaded = max(0, min(d.get('downloaded_bytes', 0), total))
                speed = d.get('speed', 0)
                if total and downloaded >= 0:
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
    def download_stream(url: str, options: dict, stream_type: str, progress_queue: Any, cancel_event: Event):
        """Download a single stream (video or audio)"""
        try:
            logger.info(f"Starting {stream_type} download for {url}")
            logger.debug(f"{stream_type.title()} download options: {options}")
            # Add status message before starting download
            progress_queue.put({'type': 'status', 'message': f'Downloading {stream_type}...'})
            def progress_hook(d):
                if cancel_event.is_set():
                    raise Exception("Download cancelled")
                YouTubeDownloader.stream_progress_hook(d, stream_type, progress_queue)
            options['progress_hooks'] = [progress_hook]
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
            logger.info(f"Finished {stream_type} download")
            
        except Exception as e:
            if str(e) == "Download cancelled":
                progress_queue.put({
                    'type': 'cancelled',
                    'message': 'Download cancelled'
                })
            else:
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
        download_folder: str,
        video_quality: str,
        audio_quality: str,
        audio_only: bool,
        progress_queue: Any,
        cancel_event: Event
    ):
        """Standalone process for downloading YouTube videos"""
        try:
            logger.info(f"Starting YouTube download process for {url}")
            progress_queue.put({'type': 'status', 'message': 'Fetching video information...'})
            
            # Get video info
            with yt_dlp.YoutubeDL() as ydl:
                info = ydl.extract_info(url, download=False)
                
            # Send title to progress queue immediately
            title = info.get('title', url)
            progress_queue.put({
                'type': 'title',
                'title': title
            })
            progress_queue.put({'type': 'status', 'message': 'Preparing download streams...'})
            
            # Create temp directory for downloads
            temp_dir = Path(download_folder) / ".temp"
            temp_dir.mkdir(exist_ok=True)
            
            # Set up queues for progress monitoring
            video_queue = mp.Queue() if not audio_only else None
            audio_queue = mp.Queue()
            
            # Create unique temp filenames
            video_temp = None if audio_only else temp_dir / f"video_{uuid.uuid4()}.mp4"
            audio_temp = temp_dir / f"audio_{uuid.uuid4()}.m4a"
            
            # Create video options if needed
            video_opts = None
            if not audio_only:
                # Get target height from video quality
                target_height = int(video_quality.split('p')[0]) if 'p' in video_quality else 0
                video_opts = {
                    'format': f'bestvideo[height<={target_height}][ext=mp4]',
                    'outtmpl': str(video_temp),
                    'quiet': True,
                    'no_warnings': True
                }
            
            # Create audio options
            audio_opts = {
                'format': 'bestaudio[ext=m4a]',
                'outtmpl': str(audio_temp),
                'quiet': True,
                'no_warnings': True
            }
            
            # Start processes list
            processes = []
            
            # Start audio download
            progress_queue.put({'type': 'status', 'message': 'Downloading...'})
            audio_process = Process(
                target=YouTubeDownloader.download_stream,
                args=(url, audio_opts, 'audio', progress_queue, cancel_event)
            )
            audio_process.start()
            processes.append(audio_process)
            
            # Start video download if needed
            if video_opts:
                progress_queue.put({'type': 'status', 'message': 'Downloading...'})
                video_process = Process(
                    target=YouTubeDownloader.download_stream,
                    args=(url, video_opts, 'video and audio', progress_queue, cancel_event)
                )
                video_process.start()
                processes.append(video_process)
                
            # Wait for downloads to complete
            for process in processes:
                process.join()
                if process.exitcode != 0:
                    # Clean up temp files
                    if video_temp and video_temp.exists():
                        video_temp.unlink()
                    if audio_temp.exists():
                        audio_temp.unlink()
                    return  # Exit early if any process failed
                    
            # Check for cancellation before muxing
            if cancel_event.is_set():
                # Clean up temp files
                if video_temp and video_temp.exists():
                    video_temp.unlink()
                if audio_temp.exists():
                    audio_temp.unlink()
                progress_queue.put({
                    'type': 'cancelled',
                    'message': 'Download cancelled'
                })
                return
                
            # Create output path
            title = info.get('title', url)
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            extension = ".m4a" if audio_only else ".mp4"
            base_output_path = Path(download_folder) / f"{safe_title}{extension}"
            output_path = ensure_unique_path(base_output_path)
            
            # Mux files if needed
            if not audio_only:
                logger.info(f"Merging files to: {output_path}")
                progress_queue.put({'type': 'status', 'message': 'Merging audio and video streams...'})
                try:
                    YouTubeDownloader.mux_files(video_temp, audio_temp, str(output_path), progress_queue, cancel_event)
                except Exception as e:
                    if str(e) == "Muxing cancelled":
                        progress_queue.put({
                            'type': 'cancelled',
                            'message': 'Download cancelled'
                        })
                    else:
                        raise
                finally:
                    # Clean up temp files
                    if video_temp and video_temp.exists():
                        video_temp.unlink()
                    if audio_temp.exists():
                        audio_temp.unlink()
            else:
                # For audio only, just rename the temp file
                os.rename(audio_temp, str(output_path))
                progress_queue.put({
                    'type': 'status', 'message': 'Finalizing download...'} )
                progress_queue.put({
                    'type': 'complete'
                })
            
        except Exception as e:
            if isinstance(e, YouTubeError) and "Download cancelled" in str(e):
                progress_queue.put({
                    'type': 'cancelled',
                    'message': 'Download cancelled'
                })
            else:
                error_msg = f"Download process failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                progress_queue.put({
                    'type': 'error',
                    'error': error_msg
                })
            
            # Clean up temp files
            if 'video_temp' in locals() and video_temp and video_temp.exists():
                video_temp.unlink()
            if 'audio_temp' in locals() and audio_temp and audio_temp.exists():
                audio_temp.unlink()
    
    @staticmethod
    def monitor_progress(progress_queue: Any, video_queue: Any = None, audio_queue: Any = None, cancel_event: Event = None) -> None:
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
                
            # Check for cancellation
            if cancel_event.is_set():
                progress_queue.put({
                    'type': 'cancelled',
                    'message': 'Download cancelled'
                })
                
        except Exception as e:
            progress_queue.put({
                'type': 'error',
                'error': str(e)
            })

    @staticmethod
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
