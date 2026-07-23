"""Derive a File's Location (physical drive/share) from its absolute path.

Pure string logic, no I/O -- Location is a property of where a file
physically lives (a directly-attached external drive, a NAS share, or the
internal boot volume), not which scan run happened to find it. See
CONTEXT.md.
"""

INTERNAL_LOCATION = "Internal"


def parse_location(path):
    """Return the Location name for an absolute path.

    On macOS, anything under /Volumes/<name>/... belongs to that external
    drive or NAS share. Anything else (e.g. under the user's home
    directory on the boot volume) is "Internal". Handles duplicated
    leading slashes defensively (seen in practice from some scan inputs)
    by splitting on "/" rather than relying on a literal string prefix.
    """
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "Volumes":
        return parts[1]
    return INTERNAL_LOCATION
