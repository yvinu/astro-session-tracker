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
    try:
        conn.execute("ALTER TABLE files ADD COLUMN target_group_id INTEGER REFERENCES target_groups(id)")
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

    Replaces all existing target group assignments -- clustering is
    recomputed from scratch each run rather than incrementally merged, so
    group ids are not stable identifiers across runs.

    Returns the number of target groups created.
    """
    now = _now()
    conn.execute("DELETE FROM target_groups")
    conn.execute("UPDATE files SET target_group_id = NULL")

    local_to_db_id = {}
    for file_id, local_group in group_of.items():
        if local_group is None:
            continue
        if local_group not in local_to_db_id:
            cursor = conn.execute(
                "INSERT INTO target_groups (created_at, updated_at) VALUES (?, ?)", (now, now)
            )
            local_to_db_id[local_group] = cursor.lastrowid
        conn.execute(
            "UPDATE files SET target_group_id = ? WHERE id = ?",
            (local_to_db_id[local_group], file_id),
        )

    conn.commit()
    return len(local_to_db_id)


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
