"""Nightly snapshot of the catalog.

The catalog holds things no rescan can rebuild -- session ratings and
notes, Rigs, Projects, Checkout manifests and lineage -- so it is copied
to a backup folder on a schedule. Uses SQLite's online backup, which is
safe while the server has the database open.
"""

import os
import re
import sqlite3
from datetime import datetime

SNAPSHOT_PATTERN = re.compile(r"^catalog-\d{8}-\d{6}\.db$")


def snapshot(db_path, backup_dir, keep=14, now=None):
    """Write a timestamped copy of the catalog into `backup_dir` and prune old ones.

    Returns the path of the snapshot written. `keep` is the number of
    snapshots retained, newest first; older ones are removed.
    """
    os.makedirs(backup_dir, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    target = os.path.join(backup_dir, f"catalog-{stamp}.db")
    partial = target + ".part"

    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(partial)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    os.replace(partial, target)

    prune(backup_dir, keep)
    return target


def snapshot_is_due(backup_dir, now, every_hours=24):
    """True when the newest snapshot is older than `every_hours`, or there is none."""
    try:
        names = sorted(f for f in os.listdir(backup_dir) if SNAPSHOT_PATTERN.match(f))
    except OSError:
        return True
    if not names:
        return True
    newest = datetime.strptime(names[-1], "catalog-%Y%m%d-%H%M%S.db")
    local_now = now.astimezone().replace(tzinfo=None) if now.tzinfo else now
    return (local_now - newest).total_seconds() >= every_hours * 3600


def prune(backup_dir, keep):
    """Remove all but the `keep` newest snapshots. Only files this module names are touched."""
    snapshots = sorted(f for f in os.listdir(backup_dir) if SNAPSHOT_PATTERN.match(f))
    removed = []
    for name in snapshots[:-keep] if keep > 0 else snapshots:
        os.remove(os.path.join(backup_dir, name))
        removed.append(name)
    return removed
