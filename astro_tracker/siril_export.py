"""Build a Siril-shaped working folder for a target group.

Symlinks a target group's files into frame_type/filter subfolders (e.g.
lights/LP/, flats/Ha/) so the group can be opened directly in Siril
without hand-sorting files that came from many different original
session folders and filters. Does not generate a Siril script (.ssf)
-- the destination folder is meant to be used with the user's own
Siril process/stacking macros.

Pure filesystem logic, no DB access -- the caller loads the group's
file records and passes them in.
"""

import os
import re
from collections import Counter

FRAME_TYPE_FOLDERS = {
    "Light": "lights",
    "Dark": "darks",
    "Bias": "biases",
    "Flat": "flats",
    "Master Light": "master_lights",
    "Master Dark": "master_darks",
    "Master Bias": "master_biases",
    "Master Flat": "master_flats",
    "Master": "master",
    "Unknown": "unknown",
}

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize(value, default):
    if not value:
        return default
    cleaned = _UNSAFE_CHARS.sub("_", str(value).strip())
    return cleaned or default


def _frame_type_folder(frame_type):
    return FRAME_TYPE_FOLDERS.get(frame_type, _sanitize(frame_type, "other"))


def _unique_destination(path):
    """Return `path`, or a copy with a numeric suffix if it already exists."""
    if not os.path.exists(path) and not os.path.islink(path):
        return path
    root, ext = os.path.splitext(path)
    n = 1
    while True:
        candidate = f"{root}_{n}{ext}"
        if not os.path.exists(candidate) and not os.path.islink(candidate):
            return candidate
        n += 1


def _pick_group_label(files):
    """Most common non-empty, non-"Unknown" target label, for naming the working folder."""
    counts = Counter(f["target"] for f in files if f.get("target") and f["target"] != "Unknown")
    if not counts:
        return "target"
    return counts.most_common(1)[0][0]


def build_working_folder(files, destination_root, group_id):
    """Symlink `files` into a Siril-shaped working folder under `destination_root`.

    `files` is an iterable of dicts with 'path', 'frame_type', 'filter',
    and 'target' keys. Creates:

        <destination_root>/<label>_group<id>/<frame_type folder>/<filter folder>/<filename>

    as symlinks to the original files. A file whose source path no
    longer exists on disk is skipped and recorded in the returned
    `missing` list rather than raising.

    Returns a summary dict: destination, counts (per frame_type/filter),
    total_linked, missing.
    """
    files = list(files)
    folder_name = f"{_sanitize(_pick_group_label(files), 'target')}_group{group_id}"
    working_dir = os.path.join(destination_root, folder_name)

    counts = {}
    missing = []
    total_linked = 0

    for f in files:
        src = f["path"]
        if not os.path.exists(src):
            missing.append(src)
            continue

        frame_folder = _frame_type_folder(f.get("frame_type"))
        filter_folder = _sanitize(f.get("filter"), "NoFilter")
        target_dir = os.path.join(working_dir, frame_folder, filter_folder)
        os.makedirs(target_dir, exist_ok=True)

        dest = _unique_destination(os.path.join(target_dir, os.path.basename(src)))
        os.symlink(src, dest)

        key = (frame_folder, filter_folder)
        counts[key] = counts.get(key, 0) + 1
        total_linked += 1

    return {
        "destination": working_dir,
        "counts": [
            {"frame_type": frame_folder, "filter": filter_folder, "count": n}
            for (frame_folder, filter_folder), n in sorted(counts.items())
        ],
        "total_linked": total_linked,
        "missing": missing,
    }
