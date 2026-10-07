"""Versioned schema migrations for the catalog.

Each migration is a function taking a connection. The database records
how many have been applied in SQLite's `user_version`, so opening a
catalog runs only what it is missing and running twice is a no-op.

Migration 1 is the schema as it stood before versioning existed. A
catalog created by an older build has those tables already and
`user_version` 0, so migration 1 has to tolerate everything it creates
being present.
"""

import sqlite3


def _add_column(conn, table, ddl):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
    except sqlite3.OperationalError:
        pass  # column already exists


def _m1_baseline(conn):
    from astro_tracker.storage import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)
    for ddl in (
        "target_group_id INTEGER REFERENCES target_groups(id)",
        "session_id INTEGER REFERENCES sessions(id)",
        "location TEXT",
        "resolution TEXT",
        "binning TEXT",
        "optical_train TEXT",
        "duplicate_group_id INTEGER REFERENCES duplicate_groups(id)",
    ):
        _add_column(conn, "files", ddl)


MIGRATIONS = [_m1_baseline]


def migrate(conn):
    """Apply every migration the database has not seen yet. Returns the resulting version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, migration in enumerate(MIGRATIONS, start=1):
        if number <= version:
            continue
        migration(conn)
        conn.execute(f"PRAGMA user_version = {number}")
        conn.commit()
    return len(MIGRATIONS)
