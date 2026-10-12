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
    """Append an error log entry. `error` may be an exception (its type name is included) or a plain string reason."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detail = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
    with open(error_log_path, 'a') as f:
        f.write(f"[{timestamp}] {file_path}: {detail}\n")


def find_image_files(directory):
    for root, _dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(IMAGE_EXTENSIONS):
                yield os.path.join(root, file)


def scan_directory(directory, db_path, error_log_path=None, progress_callback=None, should_stop=None, force=False):
    """Incrementally scan `directory` into the SQLite database at `db_path`.

    Returns a dict of counts: new, updated, skipped, failed, links, total_seen, cancelled.

    Symbolic links are counted under "links" and otherwise ignored, whether
    or not their target exists: a File is one physical copy, and a link is
    not one. Siril's `link` leaves thousands of them in `process` folders,
    usually pointing at paths that no longer exist.

    If `should_stop` is given, it's checked before each file; when it
    returns True, the walk stops early. Whatever's already been upserted
    is committed as usual (partial progress is kept, not rolled back),
    and counts["cancelled"] is set to True so callers can tell a stopped
    scan apart from one that ran to completion.

    `force=True` re-parses every file's header and re-writes its row even
    when path+mtime match what's already stored, bypassing both the
    skip-unchanged shortcut below and storage.upsert_file's own mtime
    check. Ordinary scans stay fast; this is only for backfilling fields
    that need a header re-read on files scanned before those fields
    existed (e.g. resolution/binning/optical_train) -- an explicit,
    on-demand action, never automatic.
    """
    conn = storage.connect(db_path)
    storage.init_schema(conn)

    scan_run_id = storage.start_scan_run(conn, directory)

    counts = {"new": 0, "updated": 0, "skipped": 0, "failed": 0, "links": 0, "total_seen": 0, "cancelled": False}

    for file_path in find_image_files(directory):
        if should_stop is not None and should_stop():
            counts["cancelled"] = True
            break

        counts["total_seen"] += 1

        if os.path.islink(file_path):
            counts["links"] += 1
            if progress_callback:
                progress_callback(counts, file_path, "links")
            continue

        try:
            stat = os.stat(file_path)
        except OSError as e:
            counts["failed"] += 1
            if error_log_path:
                log_error(error_log_path, file_path, str(e))
            if progress_callback:
                progress_callback(counts, file_path, "failed", str(e))
            continue

        mtime = stat.st_mtime
        existing_mtime = storage.get_file_mtime(conn, file_path)

        if not force and existing_mtime is not None and existing_mtime == mtime:
            counts["skipped"] += 1
            if progress_callback:
                progress_callback(counts, file_path, "skipped")
            continue

        parse_error = None
        try:
            meta = get_metadata(file_path)
        except Exception as e:
            meta = None
            parse_error = e

        if meta is None:
            counts["failed"] += 1
            failure_reason = str(parse_error) if parse_error is not None else "Failed to extract metadata"
            if error_log_path:
                log_error(error_log_path, file_path, parse_error if parse_error is not None else failure_reason)
            if progress_callback:
                progress_callback(counts, file_path, "failed", failure_reason)
            continue

        try:
            status = storage.upsert_file(conn, file_path, mtime, stat.st_size, meta, force=force)
        except Exception as e:
            counts["failed"] += 1
            if error_log_path:
                log_error(error_log_path, file_path, e)
            if progress_callback:
                progress_callback(counts, file_path, "failed", str(e))
            continue

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


def _print_progress(counts, file_path, status, detail=None):
    seen = counts["total_seen"]
    if seen % 10 == 0:
        print(f"Processed: {seen} ({status}) - {os.path.basename(file_path)}", end='\r')


def main():
    parser = argparse.ArgumentParser(
        description="Incrementally scan a directory for FITS/XISF files into a SQLite inventory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-d', '--directory', default=DEFAULT_SCAN_DIRECTORY,
                         help=f'Directory to scan (default: {DEFAULT_SCAN_DIRECTORY}). '
                              f'Ignored with --cluster-only.')
    parser.add_argument('--db', default=DEFAULT_DB_PATH,
                         help=f'SQLite database path (default: {DEFAULT_DB_PATH})')
    parser.add_argument('-e', '--error-log', default=DEFAULT_ERROR_LOG,
                         help=f'Error log file name (default: {DEFAULT_ERROR_LOG})')
    parser.add_argument('--cluster', action='store_true',
                         help='Accepted for old command lines; a scan now always regroups the library afterwards.')
    parser.add_argument('--cluster-only', action='store_true',
                         help='Skip the directory scan and only regroup files already in the database: '
                              'target groups, sessions, duplicates, Rig, Filter and Target names. '
                              'Ignores -d/--directory.')
    parser.add_argument('--force', action='store_true',
                         help='Re-parse every file\'s header and re-write its row even when path+mtime '
                              'match what\'s already stored. Use this once after upgrading to backfill '
                              'fields that need a header re-read (e.g. resolution/binning/optical_train) '
                              'on files scanned before those fields existed. Ordinary scans should omit '
                              'this -- it re-reads every file, unlike the normal incremental skip.')
    args = parser.parse_args()

    from astro_tracker import ingest

    if args.cluster_only:
        print(f"Database: {args.db}")
        print("Skipping directory scan (--cluster-only)")
        print("-" * 60)
        _print_derived(ingest.derive(args.db))
        return

    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory.")
        sys.exit(1)

    print(f"Scanning {args.directory}...")
    print(f"Database: {args.db}")
    if args.force:
        print("Force mode: re-parsing every file regardless of mtime")
    print("-" * 60)

    def show(update):
        if update.get("step") == "scan" and update.get("current"):
            _print_progress(update["counts"], update["current"], "scanning")

    result = ingest.run(args.db, args.directory, force=args.force, progress=show, error_log=args.error_log)
    counts = result["scan"]

    print()
    print("-" * 60)
    print("Scan complete:")
    print(f"   New files:     {counts['new']}")
    print(f"   Updated files: {counts['updated']}")
    print(f"   Unchanged (skipped): {counts['skipped']}")
    print(f"   Links (ignored): {counts['links']}")
    print(f"   Failed:        {counts['failed']}")

    if counts["failed"] > 0:
        print(f"\n{counts['failed']} file(s) failed. Check {args.error_log} for details.")

    summary = result["library"]
    print(f"\nLibrary summary ({summary['total_files']} files total):")
    print("Category breakdown:")
    for category, count in summary["category_breakdown"]:
        print(f"   {category}: {count}")
    print("Frame type breakdown:")
    for frame_type, count in summary["frame_type_breakdown"]:
        print(f"   {frame_type}: {count}")

    if result["derived"]:
        _print_derived(result["derived"])
    hashed = result["hash"]
    if hashed and not hashed.get("skipped"):
        print(f"\nContent hashes: {hashed['hashed']} computed, {hashed['failed']} failed.")


def _print_derived(summary):
    print(f"\nRA/DEC clustering: {summary['target_groups']} target group(s) found, "
          f"{summary['ungrouped_files']} file(s) ungrouped (missing/malformed coordinates).")
    if summary["orphaned_groups"] > 0:
        print(f"   Note: {summary['orphaned_groups']} previous target group(s) no longer match any current "
              f"cluster and were removed; any sessions/annotations tied to them are now orphaned.")
    print(f"\nSessions: {summary['sessions']} session(s) derived.")
    if summary["stale_sessions"] > 0:
        print(f"   Note: {summary['stale_sessions']} previous session(s) no longer match any current "
              f"grouping and were removed.")
    print(f"\nDuplicates: {summary['duplicate_groups']} duplicate group(s) found.")
    vocabulary = summary["vocabulary"]
    print(f"\nRigs: {vocabulary['rig_assigned']} file(s) assigned, "
          f"{vocabulary['rig_unassigned']} unassigned, {vocabulary['rig_ambiguous']} ambiguous.")


if __name__ == "__main__":
    main()
