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


# ---- Rigs -------------------------------------------------------------------

def _rig_from_row(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "patterns": json.loads(row["patterns"]),
        "date_ranges": json.loads(row["date_ranges"]),
    }


def get_rigs(conn):
    return [_rig_from_row(row) for row in conn.execute("SELECT * FROM rigs ORDER BY id")]


def get_rig(conn, rig_id):
    row = conn.execute("SELECT * FROM rigs WHERE id = ?", (rig_id,)).fetchone()
    return _rig_from_row(row) if row else None


def upsert_rig(conn, rig_id, name, patterns, date_ranges):
    now = _now()
    conn.execute(
        """INSERT INTO rigs (id, name, patterns, date_ranges, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET name = excluded.name, patterns = excluded.patterns,
                                         date_ranges = excluded.date_ranges, updated_at = excluded.updated_at""",
        (rig_id, name, json.dumps(patterns), json.dumps(date_ranges), now, now),
    )
    conn.commit()
    return get_rig(conn, rig_id)


def delete_rig(conn, rig_id):
    cursor = conn.execute("DELETE FROM rigs WHERE id = ?", (rig_id,))
    conn.commit()
    return cursor.rowcount > 0


def get_optical_train_summary(conn):
    """Each distinct Optical Train with its file count, date span and how its files are assigned to Rigs."""
    rows = conn.execute(
        """SELECT optical_train, COUNT(*) AS file_count, MIN(date) AS first_date, MAX(date) AS last_date,
                  GROUP_CONCAT(DISTINCT rig_id) AS rig_ids,
                  SUM(CASE WHEN rig_status = 'ambiguous' THEN 1 ELSE 0 END) AS ambiguous_count,
                  SUM(CASE WHEN rig_id IS NULL THEN 1 ELSE 0 END) AS unassigned_count
           FROM files GROUP BY optical_train ORDER BY file_count DESC"""
    ).fetchall()
    return [
        {
            "optical_train": row["optical_train"],
            "file_count": row["file_count"],
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "rig_ids": sorted((row["rig_ids"] or "").split(",")) if row["rig_ids"] else [],
            "ambiguous_count": row["ambiguous_count"],
            "unassigned_count": row["unassigned_count"],
        }
        for row in rows
    ]


# ---- Filters ----------------------------------------------------------------

def get_filter_map(conn):
    return {row["raw"]: row["canonical"] for row in conn.execute("SELECT raw, canonical FROM filter_map")}


def set_filter_mapping(conn, raw, canonical):
    """Map a header filter value (matched case-insensitively) to a canonical Filter; None removes the mapping."""
    key = str(raw or "").strip().lower()
    if canonical is None:
        conn.execute("DELETE FROM filter_map WHERE raw = ?", (key,))
    else:
        conn.execute(
            "INSERT INTO filter_map (raw, canonical) VALUES (?, ?) ON CONFLICT(raw) DO UPDATE SET canonical = excluded.canonical",
            (key, canonical),
        )
    conn.commit()


def get_filter_summary(conn):
    """Each header filter value in the library with its canonical Filter and file count."""
    rows = conn.execute(
        """SELECT filter, filter_canonical, COUNT(*) AS file_count FROM files
           GROUP BY filter, filter_canonical ORDER BY file_count DESC"""
    ).fetchall()
    return [dict(row) for row in rows]


# ---- Applying Rig and Filter to files ---------------------------------------

def get_files_for_vocabulary(conn):
    rows = conn.execute("SELECT id, optical_train, date, filter, rig_id, rig_status, filter_canonical FROM files")
    return [dict(row) for row in rows]


def save_file_vocabulary(conn, updates):
    """Write (rig_id, rig_status, filter_canonical, file_id) tuples. Does not commit."""
    conn.executemany(
        "UPDATE files SET rig_id = ?, rig_status = ?, filter_canonical = ? WHERE id = ?", updates
    )


# ---- Target names -----------------------------------------------------------

def get_target_names(conn):
    """Every target group with its canonical Target name (None until one is assigned), aliases and labels."""
    rows = conn.execute(
        """SELECT g.id AS target_group_id, n.name, n.aliases, n.is_custom,
                  COUNT(f.id) AS file_count, GROUP_CONCAT(DISTINCT f.target) AS labels
           FROM target_groups g
           LEFT JOIN target_names n ON n.target_group_id = g.id
           LEFT JOIN files f ON f.target_group_id = g.id
           GROUP BY g.id ORDER BY n.name"""
    ).fetchall()
    return [
        {
            "target_group_id": row["target_group_id"],
            "name": row["name"],
            "aliases": json.loads(row["aliases"]) if row["aliases"] else [],
            "is_custom": bool(row["is_custom"]),
            "file_count": row["file_count"],
            "labels": sorted(set((row["labels"] or "").split(","))) if row["labels"] else [],
        }
        for row in rows
    ]


def get_target_name(conn, target_group_id):
    row = conn.execute("SELECT name FROM target_names WHERE target_group_id = ?", (target_group_id,)).fetchone()
    return row["name"] if row else None


def get_target_labels_by_group(conn):
    """One OBJECT label per file, per target group -- for picking each group's majority label."""
    labels = {}
    for row in conn.execute("SELECT target_group_id, target FROM files WHERE target_group_id IS NOT NULL"):
        labels.setdefault(row["target_group_id"], []).append(row["target"])
    return labels


def set_target_name(conn, target_group_id, name, aliases=None, is_custom=True):
    """Set a target group's canonical name. Raises sqlite3.IntegrityError if another group has that name."""
    existing = conn.execute(
        "SELECT aliases FROM target_names WHERE target_group_id = ?", (target_group_id,)
    ).fetchone()
    if aliases is None:
        aliases = json.loads(existing["aliases"]) if existing else []
    conn.execute(
        """INSERT INTO target_names (target_group_id, name, aliases, is_custom, updated_at) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(target_group_id) DO UPDATE SET name = excluded.name, aliases = excluded.aliases,
                                                      is_custom = excluded.is_custom, updated_at = excluded.updated_at""",
        (target_group_id, name, json.dumps(aliases), int(is_custom), _now()),
    )
    conn.commit()
