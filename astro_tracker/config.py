"""Deployment settings, read from the environment.

The service runs in a container on the NAS, so everything that differs
between machines (where the library is mounted, where Projects and
backups go, the CLI token) comes from environment variables set in the
Compose file rather than from the database -- the catalog can then be
moved between machines without carrying machine-specific paths in it.
"""

import os


def library_roots():
    """Configured library roots as a list of (name, path), longest path first.

    ASTRO_LIBRARY_ROOTS is "Name=/path;Other=/other/path". The name is the
    Location shown for every file under that path (see location.py).
    Longest-first so a root nested inside another wins for its own files.
    """
    raw = os.environ.get("ASTRO_LIBRARY_ROOTS", "")
    roots = []
    for part in raw.split(";"):
        name, sep, path = part.partition("=")
        name, path = name.strip(), path.strip()
        if sep and name and path:
            roots.append((name, path.rstrip("/") or "/"))
    return sorted(roots, key=lambda r: len(r[1]), reverse=True)


def projects_root():
    """Folder that holds projects/<target>/<project>/, or None when unset."""
    return os.environ.get("ASTRO_PROJECTS_ROOT") or None


def backup_dir():
    return os.environ.get("ASTRO_BACKUP_DIR") or None


def backup_keep():
    return int(os.environ.get("ASTRO_BACKUP_KEEP", "14"))


def cli_token():
    """Shared secret the Mac CLI must present, or None when CLI endpoints are disabled."""
    return os.environ.get("ASTRO_CLI_TOKEN") or None


def scheduler_enabled():
    return os.environ.get("ASTRO_SCHEDULER", "").lower() in ("1", "true", "yes")


def hash_resume_delay():
    """Seconds after start before hashing resumes on its own."""
    return float(os.environ.get("ASTRO_HASH_RESUME_DELAY", "30"))
