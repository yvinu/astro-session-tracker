"""Derive a File's Location (physical drive/share) from its absolute path.

Pure string logic, no I/O -- Location is a property of where a file
physically lives (a directly-attached external drive, a NAS share, or the
internal boot volume), not which scan run happened to find it. See
CONTEXT.md.
"""

from astro_tracker import config

INTERNAL_LOCATION = "Internal"


def parse_location(path, roots=None):
    """Return the Location name for an absolute path.

    A path under a configured library root (config.library_roots, or
    `roots` when given) belongs to that root's name -- this is how the
    service running in a container on the NAS names Locations, where
    there is no /Volumes mount segment to read.

    Otherwise, on macOS, anything under /Volumes/<name>/... belongs to
    that external drive or NAS share, and anything else (e.g. under the
    user's home directory on the boot volume) is "Internal". Handles
    duplicated leading slashes defensively (seen in practice from some
    scan inputs) by splitting on "/" rather than relying on a literal
    string prefix.
    """
    if roots is None:
        roots = config.library_roots()
    parts = [p for p in path.split("/") if p]
    for name, root in roots:
        root_parts = [p for p in root.split("/") if p]
        if parts[:len(root_parts)] == root_parts:
            return name
    if len(parts) >= 2 and parts[0] == "Volumes":
        return parts[1]
    return INTERNAL_LOCATION
