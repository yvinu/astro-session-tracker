"""Duplicate detection via a metadata fingerprint.

Two Files are recognized as duplicates by (size, date, exposure, target,
instrument) rather than by content hash -- see ADR-0001. All of these are
already extracted per file, so this needs no additional I/O.

Pure logic, no I/O -- the caller is responsible for loading file records
and persisting the resulting group assignments.
"""

FINGERPRINT_FIELDS = ("size", "date", "exposure", "target", "instrument")


def _fingerprint(file):
    """Return the fingerprint tuple for a file, or None if any field is missing."""
    values = tuple(file.get(field) for field in FINGERPRINT_FIELDS)
    if any(v is None for v in values):
        return None
    return values


def find_duplicate_groups(files):
    """Group files sharing an identical (size, date, exposure, target, instrument) fingerprint.

    `files` is an iterable of dicts, each with an 'id' key (any hashable
    identifier) plus the fingerprint fields above.

    Returns a dict mapping each file's id to a zero-based group id. Files
    map to None (ungrouped) rather than raising when their fingerprint is
    incomplete (any field missing), and also when no other file shares
    their fingerprint -- a single file isn't a "duplicate group" on its
    own; membership requires at least two files.
    """
    files = list(files)

    ids_by_fingerprint = {}
    for f in files:
        fp = _fingerprint(f)
        if fp is None:
            continue
        ids_by_fingerprint.setdefault(fp, []).append(f["id"])

    group_of = {}
    next_group_id = 0
    for ids in ids_by_fingerprint.values():
        if len(ids) < 2:
            continue
        for fid in ids:
            group_of[fid] = next_group_id
        next_group_id += 1

    for f in files:
        group_of.setdefault(f["id"], None)

    return group_of
