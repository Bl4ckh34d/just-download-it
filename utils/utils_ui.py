from urllib.parse import urlparse, unquote
import re
import os


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
