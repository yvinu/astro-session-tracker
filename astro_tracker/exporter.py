"""Generate a CSV export of the SQLite inventory (source of truth is the DB, not the CSV)."""

import argparse
import csv
import io

from astro_tracker import storage
from astro_tracker.scanner import DEFAULT_DB_PATH

DEFAULT_OUTPUT_FILE = "astro_inventory_report.csv"


def records_to_csv(records):
    """Serialize a list of file-record dicts (as returned by storage.get_all_files) to a CSV string."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=storage.FILE_COLUMNS)
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue()


def export_csv(db_path, output_path):
    """Write the full current inventory to `output_path` as CSV. Returns the record count."""
    conn = storage.connect(db_path)
    try:
        records = storage.get_all_files(conn)
    finally:
        conn.close()

    with open(output_path, "w", newline="") as f:
        f.write(records_to_csv(records))

    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Export the SQLite inventory to a CSV file.")
    parser.add_argument('--db', default=DEFAULT_DB_PATH,
                         help=f'SQLite database path (default: {DEFAULT_DB_PATH})')
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT_FILE,
                         help=f'Output CSV path (default: {DEFAULT_OUTPUT_FILE})')
    args = parser.parse_args()

    count = export_csv(args.db, args.output)
    print(f"Exported {count} file records to {args.output}")


if __name__ == "__main__":
    main()
