from pathlib import Path
from urllib.parse import urlparse, unquote
import os
import re

def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube video URL"""
    patterns = [
        r'^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'^https?://(?:www\.)?youtube\.com/v/[\w-]+',
        r'^https?://youtu\.be/[\w-]+'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename"""
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    # Remove control characters
    filename = "".join(char for char in filename if ord(char) >= 32)
    return filename.strip()

def get_filename_from_url(url: str) -> str:
    """Extract filename from URL"""
    path = urlparse(url).path
    filename = unquote(os.path.basename(path))
    if not filename:
        filename = 'download'
    return sanitize_filename(filename)

def format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def format_speed(speed_bytes: float) -> str:
    """Format speed in bytes/sec to human readable string"""
    return f"{format_size(speed_bytes)}/s"

def ensure_unique_path(path: Path) -> Path:
    """Ensure path is unique by adding number suffix if needed"""
    if not path.exists():
        return path
        
    base = path.stem
    ext = path.suffix
    counter = 1
    
    while True:
        new_path = path.with_name(f"{base} ({counter}){ext}")
        if not new_path.exists():
            return new_path
        counter += 1
