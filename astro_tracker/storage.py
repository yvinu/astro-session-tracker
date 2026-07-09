"""SQLite schema and repository layer for the astro session tracker.

The database is the source of truth for scanned file metadata. CSV/JSON
exports are generated views over this store, not the other way around.
"""

import sqlite3
from datetime import datetime, timezone

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    mtime REAL NOT NULL,
    size INTEGER,
    file_name TEXT,
    folder TEXT,
    file_category TEXT,
    target TEXT,
    date TEXT,
    frame_type TEXT,
    exposure REAL,
    gain TEXT,
    temp TEXT,
    filter TEXT,
    instrument TEXT,
    ra TEXT,
    dec TEXT,
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    directory TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    new_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS target_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_group_id INTEGER NOT NULL REFERENCES target_groups(id),
    observation_night TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(target_group_id, observation_night)
);

CREATE TABLE IF NOT EXISTS session_annotations (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    rating INTEGER,
    bortle INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

FILE_COLUMNS = (
    "file_name", "folder", "file_category", "target", "date", "frame_type",
    "exposure", "gain", "temp", "filter", "instrument", "ra", "dec",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA_SQL)
    for ddl in (
        "ALTER TABLE files ADD COLUMN target_group_id INTEGER REFERENCES target_groups(id)",
        "ALTER TABLE files ADD COLUMN session_id INTEGER REFERENCES sessions(id)",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists on a previously-initialized database
    conn.commit()


def get_file_mtime(conn, path):
    """Return the stored mtime for a path, or None if it isn't tracked yet."""
    row = conn.execute("SELECT mtime FROM files WHERE path = ?", (path,)).fetchone()
    return row["mtime"] if row else None


def upsert_file(conn, path, mtime, size, metadata):
    """Insert or update a file's row based on its stored mtime.

    Returns "inserted", "updated", or "unchanged". Does not commit.
    """
    existing_mtime = get_file_mtime(conn, path)
    now = _now()

    if existing_mtime is None:
        values = [metadata.get(col) for col in FILE_COLUMNS]
        conn.execute(
            f"""INSERT INTO files
                (path, mtime, size, {", ".join(FILE_COLUMNS)}, first_seen_at, last_updated_at)
                VALUES (?, ?, ?, {", ".join(["?"] * len(FILE_COLUMNS))}, ?, ?)""",
            [path, mtime, size, *values, now, now],
        )
        return "inserted"

    if existing_mtime != mtime:
        values = [metadata.get(col) for col in FILE_COLUMNS]
        set_clause = ", ".join(f"{col} = ?" for col in FILE_COLUMNS)
        conn.execute(
            f"""UPDATE files SET mtime = ?, size = ?, {set_clause}, last_updated_at = ?
                WHERE path = ?""",
            [mtime, size, *values, now, path],
        )
        return "updated"

    return "unchanged"


def start_scan_run(conn, directory):
    cursor = conn.execute(
        "INSERT INTO scan_runs (directory, started_at) VALUES (?, ?)",
        (directory, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def finish_scan_run(conn, scan_run_id, new_count, updated_count, skipped_count, failed_count):
    conn.execute(
        """UPDATE scan_runs
           SET finished_at = ?, new_count = ?, updated_count = ?, skipped_count = ?, failed_count = ?
           WHERE id = ?""",
        (_now(), new_count, updated_count, skipped_count, failed_count, scan_run_id),
    )
    conn.commit()


def get_category_breakdown(conn):
    rows = conn.execute(
        "SELECT file_category, COUNT(*) as count FROM files GROUP BY file_category ORDER BY count DESC"
    ).fetchall()
    return [(row["file_category"], row["count"]) for row in rows]


def get_frame_type_breakdown(conn):
    rows = conn.execute(
        "SELECT frame_type, COUNT(*) as count FROM files GROUP BY frame_type ORDER BY count DESC"
    ).fetchall()
    return [(row["frame_type"], row["count"]) for row in rows]


def get_total_file_count(conn):
    row = conn.execute("SELECT COUNT(*) as count FROM files").fetchone()
    return row["count"]


def get_all_files(conn):
    """Return every file record as a list of dicts, in the CSV/API-facing column shape."""
    plain_columns = [c for c in FILE_COLUMNS if c not in ("ra", "dec")]
    query = f"""SELECT {", ".join(plain_columns)},
                       COALESCE(ra, 'Unknown') AS ra, COALESCE(dec, 'Unknown') AS dec
                FROM files
                ORDER BY folder, file_name"""
    rows = conn.execute(query).fetchall()
    columns = plain_columns + ["ra", "dec"]
    return [{col: row[col] for col in columns} for row in rows]


def get_unique_target_count(conn):
    row = conn.execute(
        "SELECT COUNT(DISTINCT target) as count FROM files WHERE target IS NOT NULL AND target != 'Unknown'"
    ).fetchone()
    return row["count"]


def get_total_exposure(conn):
    row = conn.execute("SELECT COALESCE(SUM(exposure), 0) as total FROM files").fetchone()
    return row["total"]


def get_filter_breakdown(conn):
    rows = conn.execute(
        """SELECT filter, COUNT(*) as count FROM files
           WHERE filter IS NOT NULL AND filter != 'No Filter'
           GROUP BY filter ORDER BY count DESC"""
    ).fetchall()
    return [(row["filter"], row["count"]) for row in rows]


def get_summary_stats(conn):
    category_counts = dict(get_category_breakdown(conn))
    return {
        "total_files": get_total_file_count(conn),
        "processed": category_counts.get("Processed", 0),
        "subframes": category_counts.get("Subframe", 0),
        "unique_targets": get_unique_target_count(conn),
        "total_exposure_seconds": get_total_exposure(conn),
        "category_breakdown": get_category_breakdown(conn),
        "frame_type_breakdown": get_frame_type_breakdown(conn),
        "filter_breakdown": get_filter_breakdown(conn),
    }


def get_all_files_for_clustering(conn):
    """Return every file's id + raw ra/dec, for feeding into clustering.cluster_files."""
    rows = conn.execute("SELECT id, ra, dec FROM files").fetchall()
    return [{"id": row["id"], "ra": row["ra"], "dec": row["dec"]} for row in rows]


def save_clustering(conn, group_of):
    """Persist a fresh clustering result (as returned by clustering.cluster_files).

    Clustering is always recomputed from scratch, but persisted group ids
    are kept stable across runs wherever possible: each newly computed
    cluster is matched against existing target_groups by file-membership
    overlap, and reuses the best-matching group's id rather than getting a
    fresh one. This matters because sessions and session annotations (from
    later slices) key off target_group_id -- if ids reshuffled on every
    re-cluster, annotations would silently orphan every time you scan in
    new subs for an already-known target.

    An existing group that no longer overlaps any new cluster (e.g. a
    target's clustering genuinely changed shape between runs) is dropped;
    anything keyed on its id becomes orphaned. That's expected to be rare
    -- routine re-scans that just add more subs to known targets should
    preserve every existing group's id.

    Returns (group_count, orphaned_count).
    """
    now = _now()

    existing_members = {}
    for row in conn.execute(
        "SELECT id, target_group_id FROM files WHERE target_group_id IS NOT NULL"
    ):
        existing_members.setdefault(row["target_group_id"], set()).add(row["id"])

    new_clusters = {}
    for file_id, local_group in group_of.items():
        if local_group is None:
            continue
        new_clusters.setdefault(local_group, set()).add(file_id)

    # Match each new cluster to the existing group it overlaps most, so ids
    # (and anything keyed on them) survive routine re-clustering. Each
    # existing group can be claimed by at most one new cluster.
    claimed_existing_ids = set()
    local_to_db_id = {}
    for local_group, file_ids in new_clusters.items():
        best_id, best_overlap = None, 0
        for existing_id, members in existing_members.items():
            if existing_id in claimed_existing_ids:
                continue
            overlap = len(file_ids & members)
            if overlap > best_overlap:
                best_id, best_overlap = existing_id, overlap
        if best_id is not None:
            local_to_db_id[local_group] = best_id
            claimed_existing_ids.add(best_id)
        else:
            cursor = conn.execute(
                "INSERT INTO target_groups (created_at, updated_at) VALUES (?, ?)", (now, now)
            )
            local_to_db_id[local_group] = cursor.lastrowid

    orphaned_ids = set(existing_members) - claimed_existing_ids
    for group_id in orphaned_ids:
        conn.execute("DELETE FROM target_groups WHERE id = ?", (group_id,))

    conn.execute("UPDATE files SET target_group_id = NULL")
    for local_group, file_ids in new_clusters.items():
        db_id = local_to_db_id[local_group]
        placeholders = ",".join("?" * len(file_ids))
        conn.execute(
            f"UPDATE files SET target_group_id = ? WHERE id IN ({placeholders})",
            [db_id, *file_ids],
        )
        conn.execute(
            "UPDATE target_groups SET updated_at = ? WHERE id = ?", (now, db_id)
        )

    conn.commit()
    return len(local_to_db_id), len(orphaned_ids)


def get_target_groups_summary(conn):
    """Return each target group's file count and the distinct OBJECT labels merged into it."""
    rows = conn.execute(
        """SELECT target_group_id, COUNT(*) as file_count,
                  GROUP_CONCAT(DISTINCT target) as labels
           FROM files
           WHERE target_group_id IS NOT NULL
           GROUP BY target_group_id
           ORDER BY file_count DESC"""
    ).fetchall()
    return [
        {
            "target_group_id": row["target_group_id"],
            "file_count": row["file_count"],
            "labels": sorted(set((row["labels"] or "").split(","))),
        }
        for row in rows
    ]


def get_ungrouped_file_count(conn):
    row = conn.execute("SELECT COUNT(*) as count FROM files WHERE target_group_id IS NULL").fetchone()
    return row["count"]


def get_all_files_for_sessions(conn):
    """Return every file's id + target_group_id + date, for feeding into sessions.derive_sessions."""
    rows = conn.execute("SELECT id, target_group_id, date FROM files").fetchall()
    return [{"id": row["id"], "target_group_id": row["target_group_id"], "date": row["date"]} for row in rows]


def save_sessions(conn, session_groups):
    """Persist a fresh session derivation (as returned by sessions.derive_sessions).

    Sessions have a real natural key -- (target_group_id, observation_night)
    -- so they're upserted by that key rather than needing the file-overlap
    matching target_groups requires: an existing session at the same key
    keeps its id (and thus its annotations, from a later slice, survive).
    A session whose key no longer appears in this run's derivation is
    deleted.

    Returns (session_count, stale_session_count_removed).
    """
    now = _now()
    existing = {
        (row["target_group_id"], row["observation_night"]): row["id"]
        for row in conn.execute("SELECT id, target_group_id, observation_night FROM sessions")
    }

    conn.execute("UPDATE files SET session_id = NULL")

    live_ids = set()
    for (target_group_id, night), file_ids in session_groups.items():
        key = (target_group_id, night)
        if key in existing:
            session_id = existing[key]
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        else:
            cursor = conn.execute(
                """INSERT INTO sessions (target_group_id, observation_night, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (target_group_id, night, now, now),
            )
            session_id = cursor.lastrowid
        live_ids.add(session_id)

        placeholders = ",".join("?" * len(file_ids))
        conn.execute(
            f"UPDATE files SET session_id = ? WHERE id IN ({placeholders})",
            [session_id, *file_ids],
        )

    stale_ids = set(existing.values()) - live_ids
    for session_id in stale_ids:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    conn.commit()
    return len(live_ids), len(stale_ids)


def get_sessions_summary(conn):
    """Return each session's target group, night, file count, merged OBJECT labels, and annotation."""
    rows = conn.execute(
        """SELECT s.id as session_id, s.target_group_id, s.observation_night,
                  COUNT(f.id) as file_count,
                  GROUP_CONCAT(DISTINCT f.target) as labels,
                  sa.rating as rating, sa.bortle as bortle, sa.notes as notes
           FROM sessions s
           JOIN files f ON f.session_id = s.id
           LEFT JOIN session_annotations sa ON sa.session_id = s.id
           GROUP BY s.id
           ORDER BY s.observation_night DESC, s.target_group_id"""
    ).fetchall()
    return [
        {
            "session_id": row["session_id"],
            "target_group_id": row["target_group_id"],
            "observation_night": row["observation_night"],
            "file_count": row["file_count"],
            "labels": sorted(set((row["labels"] or "").split(","))),
            "rating": row["rating"],
            "bortle": row["bortle"],
            "notes": row["notes"],
        }
        for row in rows
    ]


def get_session_annotation(conn, session_id):
    row = conn.execute(
        "SELECT * FROM session_annotations WHERE session_id = ?", (session_id,)
    ).fetchone()
    return dict(row) if row else None


def upsert_session_annotation(conn, session_id, rating=None, bortle=None, notes=None):
    """Create or update a session's manual annotation (rating/bortle/notes).

    Only fields passed as non-None are changed; omitted fields keep their
    existing stored value. This is a separate table from the auto-derived
    `sessions` row specifically so that save_sessions's re-derivation
    (which replaces sessions wholesale by natural key) never touches
    annotation data -- as long as the session's natural key still matches
    an existing session, its id is reused (see save_sessions) and this
    annotation stays attached to it untouched.
    """
    now = _now()
    existing = get_session_annotation(conn, session_id)

    if existing:
        new_rating = rating if rating is not None else existing["rating"]
        new_bortle = bortle if bortle is not None else existing["bortle"]
        new_notes = notes if notes is not None else existing["notes"]
        conn.execute(
            """UPDATE session_annotations SET rating = ?, bortle = ?, notes = ?, updated_at = ?
               WHERE session_id = ?""",
            (new_rating, new_bortle, new_notes, now, session_id),
        )
    else:
        conn.execute(
            """INSERT INTO session_annotations (session_id, rating, bortle, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, rating, bortle, notes, now, now),
        )

    conn.commit()
    return get_session_annotation(conn, session_id)
