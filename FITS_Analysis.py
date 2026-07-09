import os
import sys
import argparse
import pandas as pd
from datetime import datetime

from astro_tracker.metadata import get_metadata, normalize_frame_type  # noqa: F401 (normalize_frame_type kept for external callers)

# --- DEFAULT CONFIGURATION ---
DEFAULT_SCAN_DIRECTORY = "/Users/yvinu/Documents/AP"
DEFAULT_OUTPUT_FILE = "astro_inventory_report.csv"
DEFAULT_ERROR_LOG = "fits_analysis_errors.log"

def log_error(error_log_path, file_path, error):
    """Log failed file processing to error log.
    
    Args:
        error_log_path: Path to error log file
        file_path: Path to the file that failed
        error: Error message or exception
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_log_path, 'a') as f:
        f.write(f"[{timestamp}] {file_path}: {error}\n")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Scan directory for FITS and XISF files and generate metadata inventory report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s -d /path/to/fits/files
  %(prog)s -d /path/to/fits -o custom_report.csv
  %(prog)s -d /path/to/fits -o report.csv -e errors.log
        """
    )
    parser.add_argument(
        '-d', '--directory',
        default=DEFAULT_SCAN_DIRECTORY,
        help=f'Directory to scan for FITS/XISF files (default: {DEFAULT_SCAN_DIRECTORY})'
    )
    parser.add_argument(
        '-o', '--output',
        default=DEFAULT_OUTPUT_FILE,
        help=f'Output CSV file name (default: {DEFAULT_OUTPUT_FILE})'
    )
    parser.add_argument(
        '-e', '--error-log',
        default=DEFAULT_ERROR_LOG,
        help=f'Error log file name (default: {DEFAULT_ERROR_LOG})'
    )
    
    args = parser.parse_args()
    
    scan_directory = args.directory
    output_file = args.output
    error_log = args.error_log
    
    # Validate directory exists
    if not os.path.exists(scan_directory):
        print(f"❌ Error: Directory '{scan_directory}' does not exist.")
        sys.exit(1)
    
    if not os.path.isdir(scan_directory):
        print(f"❌ Error: '{scan_directory}' is not a directory.")
        sys.exit(1)
    
    # Clear previous error log if it exists
    if os.path.exists(error_log):
        os.remove(error_log)
    
    # Initialize counters
    data = []
    total_files = 0
    processed_files = 0
    failed_files = 0
    
    print(f"🔍 Scanning {scan_directory}...")
    print(f"📊 Output report: {output_file}")
    print(f"📝 Error log: {error_log}")
    print("-" * 60)
    
    # Count total FITS/XISF files first for progress tracking
    print("Counting files...")
    for root, dirs, files in os.walk(scan_directory):
        for file in files:
            if file.lower().endswith(('.fits', '.fit', '.fts', '.xisf')):
                total_files += 1
    
    if total_files == 0:
        print("⚠️  Warning: No FITS/XISF files found in the specified directory.")
        sys.exit(0)
    
    print(f"Found {total_files} image file(s). Processing...\n")
    
    # Process files with progress indicator
    for root, dirs, files in os.walk(scan_directory):
        for file in files:
            if file.lower().endswith(('.fits', '.fit', '.fts', '.xisf')):
                processed_files += 1
                file_path = os.path.join(root, file)
                
                # Show progress every 10 files or on last file
                if processed_files % 10 == 0 or processed_files == total_files:
                    progress = (processed_files / total_files) * 100
                    print(f"Progress: {processed_files}/{total_files} ({progress:.1f}%) - {file}", end='\r')
                
                try:
                    meta = get_metadata(file_path)
                    if meta:
                        data.append(meta)
                    else:
                        failed_files += 1
                        log_error(error_log, file_path, "Failed to extract metadata")
                except Exception as e:
                    failed_files += 1
                    log_error(error_log, file_path, str(e))
    
    print()  # New line after progress indicator
    print("-" * 60)
    
    # Generate and save report
    if data:
        df = pd.DataFrame(data)
        df.to_csv(output_file, index=False)
        print(f"✅ Report saved to {output_file}")
    else:
        print("⚠️  No valid FITS data extracted. Report not created.")
    
    # Print summary statistics
    print("\n📈 Summary Statistics:")
    print(f"   Total image files found: {total_files}")
    print(f"   Successfully processed: {processed_files - failed_files}")
    print(f"   Failed to process: {failed_files}")
    
    if failed_files > 0:
        print(f"\n⚠️  {failed_files} file(s) failed. Check {error_log} for details.")
    elif os.path.exists(error_log):
        # Remove empty error log
        os.remove(error_log)
    
    # Show breakdown by file category and frame type if data available
    if data:
        print("\n📂 File Category Breakdown:")
        category_counts = df['file_category'].value_counts()
        for category, count in category_counts.items():
            print(f"   {category}: {count}")
        
        print("\n📸 Frame Type Breakdown:")
        frame_counts = df['frame_type'].value_counts()
        for frame_type, count in frame_counts.items():
            print(f"   {frame_type}: {count}")
    
    return df if data else None

if __name__ == "__main__":
    report_df = main()