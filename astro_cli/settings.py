"""The CLI's own settings file: where the service is, the token, and how library paths map to this Mac.

The service names files by their path on the NAS (inside its container).
`path_map` says where each of those locations can be read from here:
either a folder where the share is mounted, or an rsync remote.

    {
      "server": "http://nas.local:8000",
      "token": "...",
      "work_root": "/Users/me/Temp_stacking",
      "path_map": {"/library": "/Volumes/Multimedia/AstroPhotos"}
    }
"""

import json
import os

DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".config", "astro", "config.json")


def load(path=DEFAULT_PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save(settings, path=DEFAULT_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
    os.chmod(path, 0o600)  # holds the token


class PathMapError(Exception):
    pass


def map_path(path, path_map):
    """Translate a library path as the service sees it into where this Mac reads it from.

    The longest matching prefix wins. Raises PathMapError when no prefix
    matches, naming the path, since the fix is a settings change.
    """
    for prefix in sorted(path_map or {}, key=len, reverse=True):
        clean = prefix.rstrip("/")
        if path == clean or path.startswith(clean + "/"):
            return path_map[prefix].rstrip("/") + path[len(clean):]
    raise PathMapError(
        f"No path_map entry covers '{path}'. Add one with: astro config --map <library path>=<local path or rsync remote>"
    )


def is_remote(location):
    """True for an rsync remote such as user@nas:/share/x (a colon before any slash)."""
    head = location.split("/", 1)[0]
    return ":" in head
