"""Pull new files from a device into its Source's mirror folder.

A Source's mirror is the permanent raw store for that device (ADR-0005):
a pull copies whatever the mirror is missing and changes nothing else.
The guarantees, each inherited from the user's original sync scripts or
closing a gap in them:

- The device is only ever read.
- Nothing already in the mirror is overwritten or deleted. A device file
  that differs from its mirror copy is reported, not re-fetched.
- A file is copied under a temporary name and renamed when complete, so
  an interrupted copy is never mistaken for a finished file.
- Files modified very recently are left for a later run: the device may
  still be writing them.
- The device's modification time is kept on the copy. For some devices
  it is the only evidence of a session's time zone.

This module is the transport for a share the NAS has mounted (how the
Seestar and ASIAIR appear). It has no database access; run_pull in
source_runs.py records runs and catalogs what arrived.
"""

import os
import shutil
import subprocess
import time

PART_SUFFIX = ".part"
COPY_CHUNK = 4 * 1024 * 1024

KIND_SUB = "sub"
KIND_DEVICE_PRODUCT = "device_product"

ACTION_COPY = "copy"
ACTION_PRESENT = "present"
ACTION_RECENT = "recent"
ACTION_DIFFERS = "differs"


def _in_sub_folder(rel_path):
    return any(part.endswith("_sub") for part in rel_path.split("/")[:-1])


def select_seestar(rel_path):
    """What a Seestar file is, or None if it is not pulled.

    Subs are the .fit files inside a `<target>_sub` folder; anything else
    in those folders (thumbnails, sidecars) is skipped. Everything outside
    them is the Seestar's own output -- its stacked results -- and is
    pulled as a device product.
    """
    if _in_sub_folder(rel_path):
        return KIND_SUB if rel_path.lower().endswith(".fit") else None
    return KIND_DEVICE_PRODUCT


def select_all(rel_path):
    return KIND_SUB


PROFILES = {"seestar": select_seestar, "all": select_all}


def ping(host):
    """One ping with a two-second wait. False if the host does not answer or ping is unavailable."""
    try:
        result = subprocess.run(["ping", "-c", "1", "-W", "2", host], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def is_reachable(source_dir, host=None, ping_fn=ping):
    """A device is reachable when it answers a ping (if a host is set) and its share is mounted."""
    if host and not ping_fn(host):
        return False
    return os.path.isdir(source_dir)


def plan_pull(source_dir, mirror_dir, select, now=None, stability_seconds=600):
    """Compare a device folder with its mirror and decide what to do with each selected file.

    Returns a list of dicts with rel, kind, size, mtime and action:
      copy     missing from the mirror
      present  already in the mirror with the same size
      recent   missing, but modified within the stability window
      differs  in the mirror with a different size (never overwritten)

    A file dated in the future cannot have been written a moment ago --
    it is a device clock fault -- so it is copied, not held back forever.
    """
    now = time.time() if now is None else now
    plan = []
    for root, dirs, files in os.walk(source_dir):
        dirs.sort()
        for name in sorted(files):
            if name.startswith("."):
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(src, source_dir).replace(os.sep, "/")
            kind = select(rel)
            if kind is None:
                continue
            try:
                stat = os.stat(src)
            except OSError:
                continue
            dst = os.path.join(mirror_dir, rel)
            if os.path.exists(dst):
                action = ACTION_PRESENT if os.path.getsize(dst) == stat.st_size else ACTION_DIFFERS
            elif 0 <= now - stat.st_mtime < stability_seconds:
                action = ACTION_RECENT
            else:
                action = ACTION_COPY
            plan.append({"rel": rel, "kind": kind, "size": stat.st_size, "mtime": stat.st_mtime, "action": action})
    return plan


class SourceChangedError(Exception):
    """The device file changed while it was being copied."""


def copy_file(src, dst, should_stop=None):
    """Copy one file into the mirror under a temporary name, then rename it into place.

    Returns True when the file is in place, False if stopped part-way.
    Raises SourceChangedError if the source's size or modification time
    moved during the copy; the partial copy is removed either way, so a
    file only ever appears under its final name complete.
    """
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    part = dst + PART_SUFFIX
    before = os.stat(src)
    try:
        with open(src, "rb") as fin, open(part, "wb") as fout:
            while True:
                if should_stop is not None and should_stop():
                    raise InterruptedError
                chunk = fin.read(COPY_CHUNK)
                if not chunk:
                    break
                fout.write(chunk)
            fout.flush()
            os.fsync(fout.fileno())
        after = os.stat(src)
        if (after.st_size, after.st_mtime) != (before.st_size, before.st_mtime) or os.path.getsize(part) != before.st_size:
            raise SourceChangedError(src)
        os.utime(part, (before.st_atime, before.st_mtime))
        if os.path.exists(dst):
            # Appeared since planning; the mirror never overwrites.
            os.remove(part)
            return True
        os.replace(part, dst)
        return True
    except InterruptedError:
        _remove_quietly(part)
        return False
    except BaseException:
        _remove_quietly(part)
        raise


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def pull(source_dir, mirror_dir, select, now=None, stability_seconds=600, should_stop=None, progress=None):
    """Copy every file the mirror is missing. Returns a summary dict.

    {"copied": [rel...], "bytes": n, "recent": n, "differing": [rel...],
     "present": n, "errors": [(rel, reason)...], "cancelled": bool}
    """
    summary = {"copied": [], "bytes": 0, "recent": 0, "differing": [], "present": 0, "errors": [], "cancelled": False}
    plan = plan_pull(source_dir, mirror_dir, select, now, stability_seconds)
    to_copy = [item for item in plan if item["action"] == ACTION_COPY]
    summary["present"] = sum(1 for item in plan if item["action"] == ACTION_PRESENT)
    summary["recent"] = sum(1 for item in plan if item["action"] == ACTION_RECENT)
    summary["differing"] = [item["rel"] for item in plan if item["action"] == ACTION_DIFFERS]

    for item in to_copy:
        if should_stop is not None and should_stop():
            summary["cancelled"] = True
            break
        src = os.path.join(source_dir, item["rel"])
        dst = os.path.join(mirror_dir, item["rel"])
        try:
            finished = copy_file(src, dst, should_stop)
        except SourceChangedError:
            summary["recent"] += 1
            continue
        except OSError as e:
            summary["errors"].append((item["rel"], str(e)))
            continue
        if not finished:
            summary["cancelled"] = True
            break
        summary["copied"].append(item["rel"])
        summary["bytes"] += item["size"]
        if progress:
            progress({"copied": len(summary["copied"]), "to_copy": len(to_copy), "bytes": summary["bytes"], "current": item["rel"]})
    return summary


def free_space(path):
    """Free bytes on the volume holding `path`, or None if it cannot be read."""
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None
