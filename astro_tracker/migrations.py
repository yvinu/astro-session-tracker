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


def _m2_content_hash(conn):
    for ddl in (
        "content_hash TEXT",
        "hash_size INTEGER",
        "hash_mtime REAL",
        "hashed_at TEXT",
        "hash_error TEXT",
    ):
        _add_column(conn, "files", ddl)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_content_hash ON files(content_hash)")


def _m3_vocabularies(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rigs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            patterns TEXT NOT NULL DEFAULT '[]',
            date_ranges TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS filter_map (
            raw TEXT PRIMARY KEY,
            canonical TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS target_names (
            target_group_id INTEGER PRIMARY KEY REFERENCES target_groups(id) ON DELETE CASCADE,
            name TEXT NOT NULL UNIQUE,
            aliases TEXT NOT NULL DEFAULT '[]',
            is_custom INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
    """)
    for ddl in ("rig_id TEXT", "rig_status TEXT", "filter_canonical TEXT"):
        _add_column(conn, "files", ddl)
    from astro_tracker.vocabulary import DEFAULT_FILTER_MAP
    conn.executemany(
        "INSERT OR IGNORE INTO filter_map (raw, canonical) VALUES (?, ?)", list(DEFAULT_FILTER_MAP.items())
    )


def _m4_sources(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            transport TEXT NOT NULL DEFAULT 'mounted_share',
            profile TEXT NOT NULL DEFAULT 'all',
            source_dir TEXT NOT NULL,
            mirror_dir TEXT NOT NULL,
            host TEXT,
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            stability_seconds INTEGER NOT NULL DEFAULT 600,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            outcome TEXT NOT NULL DEFAULT 'running',
            files_copied INTEGER NOT NULL DEFAULT 0,
            bytes_copied INTEGER NOT NULL DEFAULT 0,
            held_back INTEGER NOT NULL DEFAULT 0,
            differing INTEGER NOT NULL DEFAULT 0,
            detail TEXT
        );
    """)
    _add_column(conn, "files", "source_id INTEGER")


def _m5_projects(conn):
    # projects.target_group_id is deliberately not a foreign key: re-clustering
    # may drop a target group (storage.save_clustering), and a Project and its
    # manifests must outlive that. target_name keeps the name as it was.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            target_group_id INTEGER,
            target_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            number INTEGER NOT NULL,
            form TEXT NOT NULL DEFAULT 'raw',
            selection TEXT NOT NULL DEFAULT '{}',
            left_out TEXT NOT NULL DEFAULT '{}',
            working_dir TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, number)
        );
        CREATE TABLE IF NOT EXISTS checkout_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checkout_id INTEGER NOT NULL REFERENCES checkouts(id) ON DELETE CASCADE,
            file_id INTEGER,
            path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            handed_hash TEXT NOT NULL,
            session_id INTEGER,
            night TEXT,
            rig TEXT NOT NULL,
            filter TEXT NOT NULL,
            position INTEGER NOT NULL,
            exposure REAL,
            size INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_checkout_entries_checkout ON checkout_entries(checkout_id);
        CREATE INDEX IF NOT EXISTS idx_checkout_entries_hash ON checkout_entries(content_hash);
    """)


def _m6_runs_and_artifacts(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            checkout_id INTEGER REFERENCES checkouts(id),
            number INTEGER NOT NULL,
            kind TEXT NOT NULL,
            tool TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, number)
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            stage TEXT,
            original_name TEXT NOT NULL,
            original_relpath TEXT NOT NULL,
            stored_relpath TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            version INTEGER,
            rig TEXT,
            filter TEXT,
            frames INTEGER,
            exposure REAL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_artifacts_project_hash ON artifacts(project_id, content_hash);
    """)


MIGRATIONS = [_m1_baseline, _m2_content_hash, _m3_vocabularies, _m4_sources, _m5_projects, _m6_runs_and_artifacts]


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
