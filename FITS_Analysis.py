import os
import sys
import argparse
import pandas as pd
from astropy.io import fits
from datetime import datetime

# Try to import XISF support
try:
    import xisf
    XISF_AVAILABLE = True
except ImportError:
    XISF_AVAILABLE = False

# --- DEFAULT CONFIGURATION ---
DEFAULT_SCAN_DIRECTORY = "/Users/yvinu/Documents/AP"
DEFAULT_OUTPUT_FILE = "astro_inventory_report.csv"
DEFAULT_ERROR_LOG = "fits_analysis_errors.log"

def normalize_frame_type(frame_type):
    """Normalize frame type to standard values.
    
    Different software/cameras use different naming conventions.
    This function consolidates them into common types.
    
    Args:
        frame_type: Raw frame type string from header
        
    Returns:
        Normalized frame type string
    """
    if not frame_type or frame_type == "Unknown":
        return "Unknown"
    
    frame_type_str = str(frame_type).strip()
    
    # Detect malformed/corrupted header values
    # These often contain '=' or excessive whitespace indicating a raw header card
    if '=' in frame_type_str or ':' in frame_type_str or len(frame_type_str) > 50:
        return "Unknown"
    
    # Check if it's mostly whitespace with some trailing junk
    if len(frame_type_str.strip()) == 0:
        return "Unknown"
    
    frame_type_lower = frame_type_str.lower().strip()
    
    # Check for master frames first (these are processed calibration files)
    # We need to check this BEFORE the simple substring matches
    if "master" in frame_type_lower:
        if "dark" in frame_type_lower:
            return "Master Dark"
        elif "flat" in frame_type_lower:
            return "Master Flat"
        elif "bias" in frame_type_lower:
            return "Master Bias"
        elif "light" in frame_type_lower:
            return "Master Light"
        else:
            return "Master"
    
    # Map variations to standard types (for subframes)
    if "light" in frame_type_lower:
        return "Light"
    elif "dark" in frame_type_lower:
        return "Dark"
    elif "bias" in frame_type_lower:
        return "Bias"
    elif "flat" in frame_type_lower:
        return "Flat"
    elif frame_type_lower in ["0", "science"]:
        return "Light"
    elif frame_type_lower in ["1"]:
        return "Bias"
    elif frame_type_lower in ["2"]:
        return "Dark"
    elif frame_type_lower in ["3"]:
        return "Flat"
    else:
        # Return original if no match (preserves unexpected values)
        # But only if it looks like a reasonable frame type
        if len(frame_type_str) < 30 and frame_type_str.isprintable():
            return frame_type_str
        else:
            return "Unknown"

def get_xisf_metadata(file_path):
    """Extract metadata from an XISF file.
    
    Args:
        file_path: Path to the XISF file
        
    Returns:
        Dictionary of metadata if successful, None otherwise
    """
    try:
        xisf_file = xisf.XISF(file_path)
        meta = xisf_file.get_file_metadata()
        
        file_name = os.path.basename(file_path)
        
        # Determine if this is a processed file or subframe
        file_name_lower = file_name.lower()
        processed_keywords = ['stack', 'starless', 'starmask', 'master']
        is_processed = any(keyword in file_name_lower for keyword in processed_keywords)
        
        # XISF metadata is typically in FITSKeyword elements
        raw_frame_type = meta.get("IMAGETYP", meta.get("FRAMETYPE", "Unknown"))
        normalized_frame_type = normalize_frame_type(raw_frame_type)
        
        # Master frames in the header should also be marked as processed
        if normalized_frame_type.startswith("Master"):
            is_processed = True
        
        file_category = "Processed" if is_processed else "Subframe"
        return {
            "file_name": file_name,
            "folder": os.path.dirname(file_path),
            "file_category": file_category,
            "target": meta.get("OBJECT", "Unknown"),
            "date": meta.get("DATE-OBS", "Unknown"),
            "frame_type": normalize_frame_type(raw_frame_type),
            "exposure": meta.get("EXPTIME", meta.get("EXPOSURE", 0)),
            "gain": meta.get("GAIN", meta.get("ISO", "N/A")),
            "temp": meta.get("SET-TEMP", meta.get("CCD-TEMP", "N/A")),
            "filter": meta.get("FILTER", "No Filter"),
            "instrument": meta.get("INSTRUME", meta.get("INSTRUMENT", "Unknown"))
        }
    except Exception as e:
        return None

def get_fits_metadata(file_path):
    """Extract metadata from a FITS file.
    
    Args:
        file_path: Path to the FITS file
        
    Returns:
        Dictionary of metadata if successful, None otherwise
    """
    try:
        # Using 'header' only to save memory and time
        with fits.open(file_path, mode='readonly', ignore_missing_end=True) as hdul:
            header = hdul[0].header
            file_name = os.path.basename(file_path)
            
            # Determine if this is a processed file or subframe
            file_name_lower = file_name.lower()
            processed_keywords = ['stack', 'starless', 'starmask', 'master']
            is_processed = any(keyword in file_name_lower for keyword in processed_keywords)
            
            raw_frame_type = header.get("IMAGETYP", "Unknown")
            normalized_frame_type = normalize_frame_type(raw_frame_type)
            
            # Master frames in the header should also be marked as processed
            if normalized_frame_type.startswith("Master"):
                is_processed = True
            
            file_category = "Processed" if is_processed else "Subframe"
            
            return {
                "file_name": file_name,
                "folder": os.path.dirname(file_path),
                "file_category": file_category,
                "target": header.get("OBJECT", "Unknown"),
                "date": header.get("DATE-OBS", "Unknown"),
                "frame_type": normalized_frame_type,
                "exposure": header.get("EXPTIME", 0),
                "gain": header.get("GAIN", header.get("ISO", "N/A")),
                "temp": header.get("SET-TEMP", header.get("CCD-TEMP", "N/A")),
                "filter": header.get("FILTER", "No Filter"),
                "instrument": header.get("INSTRUME", "Unknown")
            }
    except Exception as e:
        return None

def get_metadata(file_path):
    """Extract metadata from a FITS or XISF file.
    
    Args:
        file_path: Path to the image file
        
    Returns:
        Dictionary of metadata if successful, None otherwise
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext == '.xisf':
        if not XISF_AVAILABLE:
            return None
        return get_xisf_metadata(file_path)
    else:
        return get_fits_metadata(file_path)

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