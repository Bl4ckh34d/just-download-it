def format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_speed(speed_bytes: float) -> str:
    """Format speed in bytes/sec to human readable string"""
    return f"{format_size(int(speed_bytes))}/s"
