class JustDownloadItError(Exception):
    """Base exception for all JustDownloadIt errors"""
    pass

class DownloadError(JustDownloadItError):
    """Error during file download"""
    pass

class YouTubeError(JustDownloadItError):
    """Error during YouTube operations"""
    pass

class ProcessError(JustDownloadItError):
    """Error in process management"""
    pass

class FFmpegError(JustDownloadItError):
    """Error during FFmpeg operations"""
    pass

class ConfigError(JustDownloadItError):
    """Error in configuration or settings"""
    pass

class BrowserCookieError(JustDownloadItError):
    """Error when accessing browser cookies"""
    pass
