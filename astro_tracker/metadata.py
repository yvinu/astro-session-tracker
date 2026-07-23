"""FITS/XISF header metadata extraction and normalization.

Shared by the legacy FITS_Analysis.py CLI and the incremental scanner.
"""

import os

from astropy.io import fits

from astro_tracker.location import parse_location

try:
    import xisf
    XISF_AVAILABLE = True
except ImportError:
    XISF_AVAILABLE = False

PROCESSED_KEYWORDS = ('stack', 'starless', 'starmask', 'master')


def normalize_frame_type(frame_type):
    """Normalize frame type to standard values.

    Different software/cameras use different naming conventions.
    This function consolidates them into common types.
    """
    if not frame_type or frame_type == "Unknown":
        return "Unknown"

    frame_type_str = str(frame_type).strip()

    # Detect malformed/corrupted header values
    # These often contain '=' or excessive whitespace indicating a raw header card
    if '=' in frame_type_str or ':' in frame_type_str or len(frame_type_str) > 50:
        return "Unknown"

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


def _is_processed(file_name, normalized_frame_type):
    file_name_lower = file_name.lower()
    is_processed = any(keyword in file_name_lower for keyword in PROCESSED_KEYWORDS)
    if normalized_frame_type.startswith("Master"):
        is_processed = True
    return is_processed


def _format_dimensions(width, height):
    """Format a (width, height) header pair as "WIDTHxHEIGHT", or "Unknown" if either is missing/malformed.

    Shared by resolution (NAXIS1/NAXIS2) and binning (XBINNING/YBINNING).
    """
    if width is None or height is None:
        return "Unknown"
    try:
        return f"{int(width)}x{int(height)}"
    except (TypeError, ValueError):
        return "Unknown"


def get_xisf_metadata(file_path):
    """Extract metadata from an XISF file, or None if extraction fails."""
    try:
        xisf_file = xisf.XISF(file_path)
        meta = xisf_file.get_file_metadata()

        file_name = os.path.basename(file_path)
        raw_frame_type = meta.get("IMAGETYP", meta.get("FRAMETYPE", "Unknown"))
        normalized_frame_type = normalize_frame_type(raw_frame_type)
        file_category = "Processed" if _is_processed(file_name, normalized_frame_type) else "Subframe"

        return {
            "file_name": file_name,
            "folder": os.path.dirname(file_path),
            "location": parse_location(file_path),
            "file_category": file_category,
            "target": meta.get("OBJECT", "Unknown"),
            "date": meta.get("DATE-OBS", "Unknown"),
            "frame_type": normalized_frame_type,
            "exposure": meta.get("EXPTIME", meta.get("EXPOSURE", 0)),
            "gain": meta.get("GAIN", meta.get("ISO", "N/A")),
            "temp": meta.get("SET-TEMP", meta.get("CCD-TEMP", "N/A")),
            "filter": meta.get("FILTER", "No Filter"),
            "instrument": meta.get("INSTRUME", meta.get("INSTRUMENT", "Unknown")),
            "resolution": _format_dimensions(meta.get("NAXIS1"), meta.get("NAXIS2")),
            "binning": _format_dimensions(meta.get("XBINNING"), meta.get("YBINNING")),
            "ra": meta.get("RA", meta.get("OBJCTRA", None)),
            "dec": meta.get("DEC", meta.get("OBJCTDEC", None)),
        }
    except Exception:
        return None


def get_fits_metadata(file_path):
    """Extract metadata from a FITS file, or None if extraction fails."""
    try:
        with fits.open(file_path, mode='readonly', ignore_missing_end=True) as hdul:
            header = hdul[0].header
            file_name = os.path.basename(file_path)

            raw_frame_type = header.get("IMAGETYP", "Unknown")
            normalized_frame_type = normalize_frame_type(raw_frame_type)
            file_category = "Processed" if _is_processed(file_name, normalized_frame_type) else "Subframe"

            return {
                "file_name": file_name,
                "folder": os.path.dirname(file_path),
                "location": parse_location(file_path),
                "file_category": file_category,
                "target": header.get("OBJECT", "Unknown"),
                "date": header.get("DATE-OBS", "Unknown"),
                "frame_type": normalized_frame_type,
                "exposure": header.get("EXPTIME", 0),
                "gain": header.get("GAIN", header.get("ISO", "N/A")),
                "temp": header.get("SET-TEMP", header.get("CCD-TEMP", "N/A")),
                "filter": header.get("FILTER", "No Filter"),
                "instrument": header.get("INSTRUME", "Unknown"),
                "resolution": _format_dimensions(header.get("NAXIS1"), header.get("NAXIS2")),
                "binning": _format_dimensions(header.get("XBINNING"), header.get("YBINNING")),
                "ra": header.get("RA", header.get("OBJCTRA", None)),
                "dec": header.get("DEC", header.get("OBJCTDEC", None)),
            }
    except Exception:
        return None


def get_metadata(file_path):
    """Extract metadata from a FITS or XISF file, or None if extraction fails."""
    file_ext = os.path.splitext(file_path)[1].lower()

    if file_ext == '.xisf':
        if not XISF_AVAILABLE:
            return None
        return get_xisf_metadata(file_path)
    else:
        return get_fits_metadata(file_path)
