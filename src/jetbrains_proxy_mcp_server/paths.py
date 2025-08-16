"""paths.py - Path normalization and conversion utilities."""

from .logger import get_logger


def normalize_path(path: str) -> str:
    """Normalizes without trimming meaningful internal double slashes (only collapse backslashes).

    Rules:
      * Strip leading/trailing whitespace.
      * Convert backslashes to forward slashes.
      * Collapse duplicate forward slashes (treat multiple as one).
    """

    if not path:
        return path

    p = path.strip().replace('\\', '/')
    while '//' in p:
        p = p.replace('//', '/')

    return p


def parse_from_wsl(p_norm: str) -> tuple[str | None, str]:
    """Extract (drive, path) from a WSL style path.

    Recognizes:
      /mnt/x/... -> drive x, /x/...
      /x/...     -> None, /x/...

    Args:
        p_norm: Normalized path (already stripped and slashes normalized).

    Returns:
        A tuple of an optional drive letter and the path:
        - Drive letter (if found), or None if no drive.
        - Path without the drive letter if found, or original path if no drive.

    See also:
        - normalize_path
    """

    import re

    if re.match(r'^/mnt/[a-z]+/', p_norm):
        parts = p_norm.split('/', 3)
        # parts[0] is empty, parts[1] is 'mnt', parts[2] is the drive letter
        if len(parts) >= 4:
            drive = parts[2]
            remainder = parts[3]
            return drive, f'/{remainder}'

    return None, p_norm


def parse_from_windows_git_bash(p_norm: str) -> tuple[str | None, str]:
    """Extract (drive, path) from a Git Bash style path.

    Recognizes:
      /x/...     -> drive x (single letter segment).

    Args:
        p_norm: Normalized path (already stripped and slashes normalized).

    Returns:
        A tuple of an optional drive letter and the path:
        - Drive letter (if found), or None if no drive.
        - Path without the drive letter if found, or original path if no drive.
    """

    import re

    if re.match(r'^/[a-z]+/', p_norm):
        parts = p_norm.split('/', 2)
        if len(parts) >= 3:
            drive = parts[1]
            remainder = parts[2]
            return drive, f'/{remainder}'

    return None, p_norm


def parse_from_windows(p_norm: str) -> tuple[str | None, str]:
    """Extract (drive, path) from a normalized Windows-style path.

    Accepts canonical forms after normalization:
      X:/... -> X:, /...
      X:     -> X:, /

    Args:
        p_norm: Normalized path (already stripped and slashes normalized).

    Returns:
        A tuple of an optional drive letter and the path:
        - Drive letter (if found), or None if no drive.
        - Path without the drive letter if found, or original path if no drive.
    """

    import re

    if re.match(r'^[A-Za-z]+:', p_norm):
        parts = p_norm.split('/', 1)
        drive = parts[0][:-1]
        remainder = parts[1] if len(parts) > 1 else ''
        return drive, f'/{remainder}'

    return None, p_norm


def detect_path_type(path: str) -> str | None:
    """Detects the path type from the path string.

    Rules:
      * /mnt/... => wsl
      * ^[A-Za-z]+: => windows (one or more letters followed by colon at start, case-insensitive)
      * otherwise None

    Args:
        path: Path string to detect type from.

    Returns:
        'wsl' if WSL style, 'windows' if Windows style, or None.
    """

    path = normalize_path(path)
    if not path:
        return None

    import re

    if re.match(r'^/mnt/[a-z]+/', path):
        return 'wsl'

    if re.match(r'^[A-Za-z]+:', path):
        return 'windows'

    return None


def detect_drive_and_path(p_norm: str, from_type: str) -> tuple[str | None, str]:
    """Determines drive and remainder given a normalized path and the declared from_type.

    Args:
        p_norm:    Normalized path (already stripped and slashes normalized).
        from_type: 'wsl', 'windows_git_bash', or 'windows'.

    Returns:
        Tuple of (drive, path) where:
            - drive is None if no drive found.
            - path is the path without the drive letter if found, or the original path if no drive.
    """

    if from_type == 'wsl':
        return parse_from_wsl(p_norm)
    if from_type == 'windows_git_bash':
        return parse_from_windows_git_bash(p_norm)
    if from_type == 'windows':
        return parse_from_windows(p_norm)

    log = get_logger()
    log.warning(f"Unknown from_type: {from_type}.")
    return None, p_norm


def build_converted_path(drive: str | None, path: str, to_type: str, original: str) -> str:
    """Construct the final path for the target type.

    Args:
        drive:    Optional drive letter.
        path:     Path without drive letter.
        to_type:  'wsl', 'windows_git_bash', or 'windows'.
        original: Original path (used when no drive is present and cannot convert).

    Returns:
        Converted path as a string based on the target type.
    """

    if to_type == 'wsl':
        if drive:
            return f"/mnt/{drive.lower()}" + path
        return path

    if to_type == 'windows_git_bash':
        if drive:
            return f"/{drive.lower()}" + path
        return path

    if to_type == 'windows':
        print(f"windows: {drive}, {path}")
        if drive:
            return f"{drive}:" + path

        # If no drive, but starts with '/', cannot convert to Windows style, return the original path
        if not path.startswith('/'):
            return path
        log = get_logger()
        log.warning(f"Failed to convert to windows style from {original} (starts with '/') without drive letter. "
                    f"Returning original.")
        return original

    log = get_logger()
    log.warning(f"Unknown to_type: {to_type}; returning original path.")
    return original


def convert_path(path: str, from_type: str, to_type: str) -> str:
    """Converts a path between style types.

    Supported types:
      windows:
        Accepts: X:\\..., X:/..., X: (root), relative, mixed slashes
      windows_git_bash:
        Accepts: /x/..., /mnt/x/..., relative (no drive)
      wsl:
        Accepts: /mnt/x/..., relative (no drive)

    Output rules:
      To wsl:
        Drive present -> /mnt/x/remainder (lowercase drive)
      To windows_git_bash:
        Drive present -> /x/remainder (lowercase drive)
      To windows:
        Drive present -> x:/remainder (forward slashes)
      No drive -> style-normalized path only
    """

    if not path \
            or from_type == to_type \
            or not to_type or (to_type not in ['wsl', 'windows_git_bash', 'windows']):
        return path

    p_type = detect_path_type(path)
    if p_type:
        if p_type == to_type:
            return path
        if p_type != from_type:
            log = get_logger()
            log.warning(f"Path {path} detected as {p_type}, but requested conversion from {from_type} to {to_type}, "
                        f"using detected type {p_type} instead.")
            from_type = p_type

    if not from_type or from_type not in ['wsl', 'windows_git_bash', 'windows']:
        log = get_logger()
        log.warning(f"Cannot convert path {path} from unknown type {from_type}. Returning original path.")
        return path

    p_norm = normalize_path(path)
    drive, p = detect_drive_and_path(p_norm, from_type)
    return build_converted_path(drive, p, to_type, path)
