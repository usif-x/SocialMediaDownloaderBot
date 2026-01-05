def format_duration(seconds: int) -> str:
    """Format duration in seconds to readable string"""
    if not seconds:
        return "Unknown"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def format_views(views: int) -> str:
    """Format view count to readable string"""
    if not views:
        return "Unknown"

    if views >= 1_000_000_000:
        return f"{views / 1_000_000_000:.1f}B"
    elif views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    elif views >= 1_000:
        return f"{views / 1_000:.1f}K"
    else:
        return str(views)


def format_file_size(size_bytes: int) -> str:
    """Format file size in bytes to readable string"""
    if not size_bytes:
        return "Unknown"

    if size_bytes >= 1_073_741_824:  # GB
        return f"{size_bytes / 1_073_741_824:.2f} GB"
    elif size_bytes >= 1_048_576:  # MB
        return f"{size_bytes / 1_048_576:.2f} MB"
    elif size_bytes >= 1024:  # KB
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} B"
