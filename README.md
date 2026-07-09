# FITS/XISF Analysis Tool

A Python tool to scan directories for astronomy image files (FITS and XISF formats) and generate comprehensive metadata inventory reports.

## Features

- **Multiple Format Support**: Handles FITS (.fits, .fit, .fts) and XISF (.xisf) files
- **Intelligent Classification**: Automatically categorizes files as "Processed" or "Subframe" based on filename patterns
- **Real-time Progress**: Live progress tracking during scanning
- **Error Logging**: Detailed error logs for files that fail to process
- **Summary Statistics**: Comprehensive breakdown by file category and frame type
- **Flexible Configuration**: Command-line arguments for custom directories and output files

## Installation

### Required Dependencies

```bash
# Core dependencies (required)
pip install pandas astropy

# XISF support (optional but recommended)
pip install xisf
```

**Note**: The script will work without the `xisf` library, but XISF files will be skipped during processing.

## Usage

### Basic Usage
```bash
# Use default settings
python3 FITS_Analysis.py

# Scan a specific directory
python3 FITS_Analysis.py -d /path/to/your/images

# Custom output file
python3 FITS_Analysis.py -o my_inventory.csv

# All custom options
python3 FITS_Analysis.py -d /path/to/images -o report.csv -e errors.log
```

### Command-Line Options

- `-d, --directory`: Directory to scan (default: `/Users/yvinu/Documents/AP`)
- `-o, --output`: Output CSV filename (default: `astro_inventory_report.csv`)
- `-e, --error-log`: Error log filename (default: `fits_analysis_errors.log`)
- `-h, --help`: Show help message

## Output Format

### CSV Report Columns

| Column | Description |
|--------|-------------|
| `file_name` | Name of the image file |
| `folder` | Directory path containing the file |
| `file_category` | "Processed" or "Subframe" based on filename |
| `target` | Astronomical object name (from OBJECT header) |
| `date` | Observation date (from DATE-OBS header) |
| `frame_type` | Type of frame (Light, Dark, Bias, Flat, etc.) |
| `exposure` | Exposure time in seconds |
| `gain` | Camera gain or ISO setting |
| `temp` | Camera temperature |
| `filter` | Filter name used |
| `instrument` | Camera/instrument name |

### File Classification

Files are automatically classified based on their filenames:

- **Processed**: Files containing "stack", "starless", or "starmask" (case-insensitive)
  - Examples: `M42_stacked.fits`, `nebula_starless.xisf`, `galaxy_StarMask.fit`
- **Subframe**: All other files (raw calibration and light frames)

### Console Output Example

```
🔍 Scanning /Users/yvinu/Documents/AP...
📊 Output report: astro_inventory_report.csv
📝 Error log: fits_analysis_errors.log
------------------------------------------------------------
Counting files...
Found 1232 image file(s). Processing...

Progress: 1232/1232 (100.0%) - M42_light_100.fits
------------------------------------------------------------
✅ Report saved to astro_inventory_report.csv

📈 Summary Statistics:
   Total image files found: 1232
   Successfully processed: 1223
   Failed to process: 9

⚠️  9 file(s) failed. Check fits_analysis_errors.log for details.

📂 File Category Breakdown:
   Subframe: 1044
   Processed: 179

📸 Frame Type Breakdown:
   Light: 868
   Light Frame: 218
   Flat Frame: 57
   Flat: 24
   Dark Frame: 16
   Bias Frame: 11
```

## Live Dashboard (incremental scanner + API server)

The `astro_tracker` package adds an incremental, SQLite-backed alternative to the one-shot CSV workflow above:

```bash
# Scan into a SQLite database (only new/changed files are re-parsed on repeat runs)
python3 -m astro_tracker.scanner -d /path/to/images --db astro_inventory.db

# Serve the dashboard + a local read API over that database
python3 -m astro_tracker.server --db astro_inventory.db
```

Then open `http://127.0.0.1:8000` — `dashboard.html` now loads live from the local API instead of requiring a manual CSV upload. Re-run the scanner anytime; unchanged files are skipped, so repeat scans on a growing library are fast.

## Troubleshooting

### XISF Files Not Processing

If XISF files are being skipped, ensure the `xisf` library is installed:
```bash
pip install xisf
```

### Import Errors

If you see `ModuleNotFoundError` for pandas or astropy:
```bash
pip install pandas astropy
```

### Empty or Missing Metadata

Some files may have incomplete headers. These files will still be included in the report with "Unknown" or "N/A" values for missing fields.

## Error Log

Failed files are logged to `fits_analysis_errors.log` with timestamps:
```
[2026-01-06 21:58:00] /path/to/file.fits: Failed to extract metadata
[2026-01-06 21:58:01] /path/to/corrupt.xisf: OSError: Invalid file format
```

## Notes

- Progress updates appear every 10 files
- The error log is only created if there are failures
- Metadata extraction is read-only and does not modify files
- The script recursively scans all subdirectories
