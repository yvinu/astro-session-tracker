"""Content hashes for catalogued Files.

A Content hash is the SHA-256 of a file's bytes. It is what lets the app
say two copies are exactly the same file, which the Duplicate Fingerprint
(size + header fields, see duplicates.py and ADR-0001) cannot: a
truncated or corrupted copy of the right size has the same fingerprint.
The fingerprint stays the fast way to *find* candidate duplicates; a
Content hash is what any delete must rest on.

Hashing reads every byte, so it runs as a background pass over files
that have no hash yet, or whose size or modification time has changed
since they were hashed.
"""

import argparse
import hashlib
import os

from astro_tracker import library_storage, storage

CHUNK_SIZE = 1024 * 1024

VERIFY_OK = "ok"
VERIFY_STALE = "stale"
VERIFY_MISMATCH = "mismatch"
VERIFY_MISSING = "missing"


def hash_file(path, should_stop=None):
    """Return the SHA-256 hex digest of a file's bytes, or None if stopped part-way."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            if should_stop is not None and should_stop():
                return None
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path, content_hash, hash_size, hash_mtime):
    """Check a file on disk against the hash recorded for it.

    "stale" means the file's size or modification time no longer match
    what they were when it was hashed -- it has changed and needs
    re-hashing, which is a different situation from "mismatch", where
    the file looks untouched but its bytes hash differently (corruption).
    """
    try:
        stat = os.stat(path)
    except OSError:
        return VERIFY_MISSING
    if stat.st_size != hash_size or stat.st_mtime != hash_mtime:
        return VERIFY_STALE
    return VERIFY_OK if hash_file(path) == content_hash else VERIFY_MISMATCH


def hash_pending(db_path, path_prefixes=None, should_stop=None, progress=None):
    """Hash every catalogued file that has no current Content hash.

    Each file is committed as it finishes, so stopping and restarting
    loses at most the file in flight and never re-hashes one whose size
    and modification time are unchanged. An unreadable file is recorded
    as failed and the pass carries on.

    `path_prefixes` limits the pass to files under those directories.
    `progress` is called with a dict of counts after each file.

    Returns {"hashed": n, "failed": n, "total": n, "cancelled": bool}.
    """
    conn = storage.connect(db_path)
    storage.init_schema(conn)
    pending = library_storage.get_files_needing_hash(conn, path_prefixes)
    counts = {"hashed": 0, "failed": 0, "total": len(pending), "cancelled": False}

    for row in pending:
        if should_stop is not None and should_stop():
            counts["cancelled"] = True
            break
        try:
            stat = os.stat(row["path"])
            digest = hash_file(row["path"], should_stop)
        except OSError as e:
            library_storage.set_hash_error(conn, row["id"], str(e))
            counts["failed"] += 1
        else:
            if digest is None:
                counts["cancelled"] = True
                break
            library_storage.set_content_hash(conn, row["id"], digest, stat.st_size, stat.st_mtime)
            counts["hashed"] += 1
        conn.commit()
        if progress:
            progress(dict(counts, current=row["path"]))

    conn.close()
    return counts


def main():
    parser = argparse.ArgumentParser(description="Compute Content hashes for catalogued files that lack one.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--under", action="append", metavar="DIR",
                        help="Only hash files under this directory. Repeatable. Default: everything.")
    args = parser.parse_args()

    def show(counts):
        done = counts["hashed"] + counts["failed"]
        print(f"Hashed {done}/{counts['total']} - {os.path.basename(counts['current'])}", end="\r")

    counts = hash_pending(args.db, args.under, progress=show)
    print(f"\nHashed: {counts['hashed']}  Failed: {counts['failed']}  Total pending: {counts['total']}")


if __name__ == "__main__":
    main()
