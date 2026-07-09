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
