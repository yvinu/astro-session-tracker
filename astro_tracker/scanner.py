"""Incremental FITS/XISF directory scanner.

Walks a directory for FITS/XISF files and upserts their metadata into
SQLite, skipping files whose path + modification time haven't changed
since the last scan.
"""

import argparse
import os
import sys
from datetime import datetime

from astro_tracker import storage
from astro_tracker.metadata import get_metadata

DEFAULT_SCAN_DIRECTORY = "/Users/yvinu/Documents/AP"
DEFAULT_DB_PATH = "astro_inventory.db"
DEFAULT_ERROR_LOG = "fits_analysis_errors.log"

IMAGE_EXTENSIONS = ('.fits', '.fit', '.fts', '.xisf')


def log_error(error_log_path, file_path, error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_log_path, 'a') as f:
        f.write(f"[{timestamp}] {file_path}: {error}\n")


def find_image_files(directory):
    for root, _dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(IMAGE_EXTENSIONS):
                yield os.path.join(root, file)


def scan_directory(directory, db_path, error_log_path=None, progress_callback=None):
    """Incrementally scan `directory` into the SQLite database at `db_path`.

    Returns a dict of counts: new, updated, skipped, failed, total_seen.
    """
    conn = storage.connect(db_path)
    storage.init_schema(conn)

    scan_run_id = storage.start_scan_run(conn, directory)

    counts = {"new": 0, "updated": 0, "skipped": 0, "failed": 0, "total_seen": 0}

    for file_path in find_image_files(directory):
        counts["total_seen"] += 1

        try:
            stat = os.stat(file_path)
        except OSError as e:
            counts["failed"] += 1
            if error_log_path:
                log_error(error_log_path, file_path, str(e))
            continue

        mtime = stat.st_mtime
        existing_mtime = storage.get_file_mtime(conn, file_path)

        if existing_mtime is not None and existing_mtime == mtime:
            counts["skipped"] += 1
            if progress_callback:
                progress_callback(counts, file_path, "skipped")
            continue

        try:
            meta = get_metadata(file_path)
        except Exception as e:
            meta = None
            if error_log_path:
                log_error(error_log_path, file_path, str(e))

        if meta is None:
            counts["failed"] += 1
            if error_log_path:
                log_error(error_log_path, file_path, "Failed to extract metadata")
            if progress_callback:
                progress_callback(counts, file_path, "failed")
            continue

        status = storage.upsert_file(conn, file_path, mtime, stat.st_size, meta)
        status_to_count_key = {"inserted": "new", "updated": "updated", "unchanged": "skipped"}
        count_key = status_to_count_key[status]
        counts[count_key] += 1
        if progress_callback:
            progress_callback(counts, file_path, count_key)

    conn.commit()
    storage.finish_scan_run(
        conn, scan_run_id,
        counts["new"], counts["updated"], counts["skipped"], counts["failed"],
    )
    conn.close()

    return counts


def _print_progress(counts, file_path, status):
    seen = counts["total_seen"]
    if seen % 10 == 0:
        print(f"Processed: {seen} ({status}) - {os.path.basename(file_path)}", end='\r')


def main():
    parser = argparse.ArgumentParser(
        description="Incrementally scan a directory for FITS/XISF files into a SQLite inventory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-d', '--directory', default=DEFAULT_SCAN_DIRECTORY,
                         help=f'Directory to scan (default: {DEFAULT_SCAN_DIRECTORY})')
    parser.add_argument('--db', default=DEFAULT_DB_PATH,
                         help=f'SQLite database path (default: {DEFAULT_DB_PATH})')
    parser.add_argument('-e', '--error-log', default=DEFAULT_ERROR_LOG,
                         help=f'Error log file name (default: {DEFAULT_ERROR_LOG})')
    parser.add_argument('--cluster', action='store_true',
                         help='Recompute RA/DEC target-group clustering after scanning')
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory.")
        sys.exit(1)

    print(f"Scanning {args.directory}...")
    print(f"Database: {args.db}")
    print("-" * 60)

    counts = scan_directory(args.directory, args.db, args.error_log, progress_callback=_print_progress)

    print()
    print("-" * 60)
    print("Scan complete:")
    print(f"   New files:     {counts['new']}")
    print(f"   Updated files: {counts['updated']}")
    print(f"   Unchanged (skipped): {counts['skipped']}")
    print(f"   Failed:        {counts['failed']}")

    if counts["failed"] > 0:
        print(f"\n{counts['failed']} file(s) failed. Check {args.error_log} for details.")

    conn = storage.connect(args.db)
    total = storage.get_total_file_count(conn)
    print(f"\nLibrary summary ({total} files total):")
    print("Category breakdown:")
    for category, count in storage.get_category_breakdown(conn):
        print(f"   {category}: {count}")
    print("Frame type breakdown:")
    for frame_type, count in storage.get_frame_type_breakdown(conn):
        print(f"   {frame_type}: {count}")

    if args.cluster:
        from astro_tracker import clustering
        files = storage.get_all_files_for_clustering(conn)
        group_of = clustering.cluster_files(files)
        n_groups, n_orphaned = storage.save_clustering(conn, group_of)
        ungrouped = storage.get_ungrouped_file_count(conn)
        print(f"\nRA/DEC clustering: {n_groups} target group(s) found, {ungrouped} file(s) ungrouped "
              f"(missing/malformed coordinates).")
        if n_orphaned > 0:
            print(f"   Note: {n_orphaned} previous target group(s) no longer match any current "
                  f"cluster and were removed; any sessions/annotations tied to them are now orphaned.")

        from astro_tracker import sessions as sessions_module
        session_files = storage.get_all_files_for_sessions(conn)
        session_groups = sessions_module.derive_sessions(session_files)
        n_sessions, n_stale_sessions = storage.save_sessions(conn, session_groups)
        print(f"\nSessions: {n_sessions} session(s) derived.")
        if n_stale_sessions > 0:
            print(f"   Note: {n_stale_sessions} previous session(s) no longer match any current "
                  f"grouping and were removed.")

    conn.close()


if __name__ == "__main__":
    main()
