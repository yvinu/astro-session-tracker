"""One-time move of an existing catalog to a machine where the library is mounted elsewhere.

The catalog keys every File by absolute path. On the Mac the NAS share
is /Volumes/<share>/...; inside the container on the NAS the same files
sit under a different mount point. This rewrites the stored paths from
one prefix to the other so the catalog keeps describing the same files,
and session annotations, which hang off sessions and target groups
rather than paths, come along untouched.

Location is deliberately left as stored: name the library root in
ASTRO_LIBRARY_ROOTS after the old volume (e.g. "Multimedia=/library")
and new scans produce the same Location the old rows already carry.

    python -m astro_tracker.migrate_catalog --db catalog.db \\
        --map /Volumes/Multimedia=/library
"""

import argparse

from astro_tracker import storage


def rewrite_prefix(path, old, new):
    """Return `path` with a leading `old` directory prefix replaced by `new`, or None if it doesn't start with it."""
    old = old.rstrip("/")
    new = new.rstrip("/")
    if path == old:
        return new or "/"
    if path.startswith(old + "/"):
        return new + path[len(old):]
    return None


def rewrite_paths(conn, mappings):
    """Rewrite files.path/folder and scan_runs.directory for each (old, new) prefix.

    A file whose new path is already taken by another row is left alone
    and counted as a conflict rather than overwriting that row.

    Returns {"rewritten": n, "conflicts": n, "untouched": n}.
    """
    counts = {"rewritten": 0, "conflicts": 0, "untouched": 0}
    rows = conn.execute("SELECT id, path, folder FROM files").fetchall()
    taken = {row["path"] for row in rows}

    for row in rows:
        new_path = None
        for old, new in mappings:
            new_path = rewrite_prefix(row["path"], old, new)
            if new_path is not None:
                new_folder = rewrite_prefix(row["folder"] or "", old, new) or row["folder"]
                break
        if new_path is None or new_path == row["path"]:
            counts["untouched"] += 1
            continue
        if new_path in taken:
            counts["conflicts"] += 1
            continue
        conn.execute("UPDATE files SET path = ?, folder = ? WHERE id = ?", (new_path, new_folder, row["id"]))
        taken.discard(row["path"])
        taken.add(new_path)
        counts["rewritten"] += 1

    for row in conn.execute("SELECT id, directory FROM scan_runs").fetchall():
        for old, new in mappings:
            new_dir = rewrite_prefix(row["directory"], old, new)
            if new_dir is not None:
                conn.execute("UPDATE scan_runs SET directory = ? WHERE id = ?", (new_dir, row["id"]))
                break

    conn.commit()
    return counts


def main():
    parser = argparse.ArgumentParser(description="Rewrite stored paths in a catalog for a new mount point.")
    parser.add_argument("--db", required=True, help="Catalog to rewrite in place (copy it first)")
    parser.add_argument("--map", action="append", required=True, metavar="OLD=NEW",
                        help="Path prefix to replace, e.g. /Volumes/Multimedia=/library. Repeatable.")
    args = parser.parse_args()

    mappings = []
    for item in args.map:
        old, sep, new = item.partition("=")
        if not sep or not old or not new:
            parser.error(f"--map expects OLD=NEW, got '{item}'")
        mappings.append((old, new))

    conn = storage.connect(args.db)
    storage.init_schema(conn)
    before = conn.execute("SELECT COUNT(*) FROM session_annotations").fetchone()[0]
    counts = rewrite_paths(conn, mappings)
    after = conn.execute("SELECT COUNT(*) FROM session_annotations").fetchone()[0]
    conn.close()

    print(f"Rewritten: {counts['rewritten']}  Untouched: {counts['untouched']}  Conflicts: {counts['conflicts']}")
    print(f"Session annotations: {before} before, {after} after")


if __name__ == "__main__":
    main()
