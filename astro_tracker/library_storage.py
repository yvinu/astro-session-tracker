"""Repository layer for the library-manager tables.

Companion to storage.py, which holds the inventory tables (files, scan
runs, target groups, sessions, duplicates). This module holds what the
library manager added on top: Content hashes, Rigs and the other
vocabularies, Sources and their runs, Projects, Checkouts, Runs and
Artifacts. Kept separate only for size -- the rule is the same: no raw
SQL outside the two storage modules.
"""

import json
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


def _under_prefixes_clause(prefixes, column="path"):
    """Build a clause matching rows whose `column` is under any of the given directories."""
    if not prefixes:
        return "", []
    parts, params = [], []
    for prefix in prefixes:
        prefix = prefix.rstrip("/")
        parts.append(f"{column} LIKE ? ESCAPE '\\'")
        params.append(prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%")
    return "(" + " OR ".join(parts) + ")", params


# ---- Content hashes ---------------------------------------------------------

def get_files_needing_hash(conn, path_prefixes=None):
    """Files with no Content hash, or whose size/mtime changed since they were hashed.

    The scanner updates files.size and files.mtime when a file changes on
    disk, so comparing them with the values recorded at hashing time is
    how a changed file gets picked up again without re-reading anything.
    """
    where = "(content_hash IS NULL OR hash_size IS NOT size OR hash_mtime IS NOT mtime)"
    clause, params = _under_prefixes_clause(path_prefixes)
    if clause:
        where += f" AND {clause}"
    rows = conn.execute(f"SELECT id, path FROM files WHERE {where} ORDER BY path", params).fetchall()
    return [dict(row) for row in rows]


def set_content_hash(conn, file_id, content_hash, size, mtime):
    """Record a file's Content hash together with the size and mtime it was computed at.

    files.size/mtime are brought in line with what was actually hashed,
    so a file that changed between the scan and the hashing pass is not
    reported as needing a hash again straight away.
    """
    conn.execute(
        """UPDATE files SET content_hash = ?, hash_size = ?, hash_mtime = ?, hashed_at = ?,
                            hash_error = NULL, size = ?, mtime = ?
           WHERE id = ?""",
        (content_hash, size, mtime, _now(), size, mtime, file_id),
    )


def set_hash_error(conn, file_id, error):
    conn.execute(
        "UPDATE files SET content_hash = NULL, hash_error = ?, hashed_at = ? WHERE id = ?",
        (error, _now(), file_id),
    )


def get_hash_counts(conn):
    row = conn.execute(
        """SELECT
             SUM(CASE WHEN content_hash IS NOT NULL AND hash_size IS size AND hash_mtime IS mtime THEN 1 ELSE 0 END) AS hashed,
             SUM(CASE WHEN hash_error IS NOT NULL AND content_hash IS NULL THEN 1 ELSE 0 END) AS failed,
             COUNT(*) AS total
           FROM files"""
    ).fetchone()
    hashed, failed, total = row["hashed"] or 0, row["failed"] or 0, row["total"] or 0
    return {"hashed": hashed, "failed": failed, "pending": total - hashed - failed, "total": total}


def get_files_by_hash(conn, content_hash):
    rows = conn.execute(
        "SELECT id, path, location, size FROM files WHERE content_hash = ? ORDER BY path", (content_hash,)
    ).fetchall()
    return [dict(row) for row in rows]
