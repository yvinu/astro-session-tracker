"""FITS Header Analysis Module.

Provides detailed statistical analysis of FITS header cards, field combinations,
candidates for standardization, and software publisher identification across
scanned FITS collections.
"""

import os
from collections import Counter, defaultdict
from astropy.io import fits

try:
    import xisf
    XISF_AVAILABLE = True
except ImportError:
    XISF_AVAILABLE = False


# Known attribute synonym maps for standardization analysis
KNOWN_SYNONYMS = {
    "Exposure Time": ["EXPTIME", "EXPOSURE"],
    "Gain / ISO": ["GAIN", "ISO", "EGAIN", "CCDGAIN"],
    "Sensor / Target Temperature": ["SET-TEMP", "CCD-TEMP", "TEMP", "COOLPOWER"],
    "Target / Object Name": ["OBJECT", "OBJCT", "TARGET"],
    "Frame Type": ["IMAGETYP", "FRAMETYPE", "FRAME"],
    "Right Ascension": ["RA", "OBJCTRA", "CRVAL1"],
    "Declination": ["DEC", "OBJCTDEC", "CRVAL2"],
    "Camera / Instrument": ["INSTRUME", "INSTRUMENT", "CAMERA", "DETECTOR"],
    "Telescope / Optics": ["TELESCOP", "TELESCOPE", "SCOPE"],
    "Software / Publisher": ["SWCREATE", "CREATOR", "PROGRAM", "SOFTWARE", "ORIGIN"],
    "Filter Name": ["FILTER", "FILTER1", "FILTER2", "FILT"],
    "Binning": ["XBINNING", "YBINNING", "BINNING", "BINNINGX", "BINNINGY"],
    "Pixel Size": ["PIXSIZE", "XPIXSZ", "YPIXSZ", "PIXSIZE1", "PIXSIZE2"],
    "Focal Length": ["FOCALLEN", "FOCAL"],
    "Site Coordinates": ["SITELAT", "SITELONG", "LATITUDE", "LONGITUDE", "GEOLAT", "GEOLON"],
    "Bayer Pattern": ["BAYERPAT", "Bayer-Pattern", "COLORTYP"],
    "Observation Date": ["DATE-OBS", "DATE", "DATE_OBS"],
}


def extract_header_keys_and_values(file_path):
    """Extract clean header keys and sample values from a FITS or XISF file.

    Returns:
        dict: {key: sample_value} for the file header.
    """
    ext = os.path.splitext(file_path)[1].lower()
    header_data = {}

    if ext == ".xisf":
        if not XISF_AVAILABLE:
            return None
        try:
            xfile = xisf.XISF(file_path)
            meta = xfile.get_file_metadata()
            for k, v in meta.items():
                if k and isinstance(k, str):
                    header_data[k.upper().strip()] = str(v)
            return header_data
        except Exception:
            return None

    try:
        with fits.open(file_path, mode='readonly', ignore_missing_end=True) as hdul:
            if len(hdul) == 0:
                return None
            header = hdul[0].header
            for card in header.cards:
                key = card.keyword
                if key and isinstance(key, str) and key.strip():
                    key_clean = key.strip()
                    if key_clean not in header_data:
                        val = card.value
                        header_data[key_clean] = "" if val is None else str(val)
            return header_data
    except Exception:
        return None


def extract_software_publishers(file_path, header_data):
    """Identify software editors or publishers from header fields or comments.

    Args:
        file_path: Path to the FITS file
        header_data: Extracted key-value dict

    Returns:
        list of string software signatures detected
    """
    publishers = set()

    # Direct card values
    sw_cards = ["SWCREATE", "CREATOR", "PROGRAM", "SOFTWARE", "ORIGIN"]
    for card in sw_cards:
        val = header_data.get(card, "")
        if val and val != "Unknown":
            publishers.add(val.strip())

    # Direct check inside HISTORY or COMMENT or INSTRUME if present
    ext = os.path.splitext(file_path)[1].lower()
    if ext in [".fits", ".fit", ".fts"]:
        try:
            with fits.open(file_path, mode='readonly', ignore_missing_end=True) as hdul:
                if len(hdul) > 0:
                    header = hdul[0].header
                    history_str = " ".join([str(c) for c in header.get('HISTORY', [])])
                    comment_str = " ".join([str(c) for c in header.get('COMMENT', [])])
                    full_text = f"{history_str} {comment_str}".lower()

                    if "pixinsight" in full_text:
                        publishers.add("PixInsight")
                    if "siril" in full_text:
                        publishers.add("Siril")
                    if "asiair" in full_text:
                        publishers.add("ASIAIR")
                    if "sharpcap" in full_text:
                        publishers.add("SharpCap")
                    if "n.i.n.a" in full_text or "nina" in full_text:
                        publishers.add("N.I.N.A.")
                    if "astro pixel processor" in full_text:
                        publishers.add("Astro Pixel Processor")
        except Exception:
            pass

    if not publishers:
        publishers.add("Unknown / Unspecified")

    return sorted(list(publishers))


def analyze_fits_headers(scan_directory, progress_callback=None):
    """Scan directory recursively and generate comprehensive FITS header statistics.

    Returns dict containing structured answers to all 5 questions.
    """
    files_to_scan = []
    for root, dirs, files in os.walk(scan_directory):
        for file in files:
            if file.lower().endswith(('.fits', '.fit', '.fts', '.xisf')):
                files_to_scan.append(os.path.join(root, file))

    total_files = len(files_to_scan)
    if total_files == 0:
        return {
            "total_files": 0,
            "processed_files": 0,
            "failed_files": 0,
            "common_field_sets": [],
            "unique_combinations": [],
            "unique_fields_list": [],
            "standardization_candidates": [],
            "software_publishers": []
        }

    processed_count = 0
    failed_count = 0

    key_set_counter = Counter()
    all_keys_counter = Counter()
    key_sample_values = defaultdict(list)
    software_counter = Counter()
    combination_files = defaultdict(list)

    for idx, file_path in enumerate(files_to_scan, 1):
        if progress_callback:
            progress_callback(idx, total_files, file_path)

        header_data = extract_header_keys_and_values(file_path)
        if not header_data:
            failed_count += 1
            continue

        processed_count += 1
        keys = tuple(sorted(header_data.keys()))
        key_set = frozenset(keys)

        key_set_counter[key_set] += 1
        combination_files[key_set].append(os.path.basename(file_path))

        for k, v in header_data.items():
            all_keys_counter[k] += 1
            if v and len(key_sample_values[k]) < 5:
                if v not in key_sample_values[k]:
                    key_sample_values[k].append(v)

        # Software / publisher detection
        pubs = extract_software_publishers(file_path, header_data)
        for p in pubs:
            software_counter[p] += 1

    # --- 1) Most common set of fields or cards ---
    most_common_sets = []
    for rank, (k_set, count) in enumerate(key_set_counter.most_common(), 1):
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        most_common_sets.append({
            "rank": rank,
            "field_count": len(k_set),
            "file_count": count,
            "percentage": round(pct, 2),
            "fields": sorted(list(k_set))
        })

    # --- 2) Unique combinations of FITS fields ---
    unique_combinations = []
    most_common_keys = set(most_common_sets[0]["fields"]) if most_common_sets else set()

    for rank, (k_set, count) in enumerate(key_set_counter.most_common(), 1):
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        current_keys = set(k_set)
        added_keys = sorted(list(current_keys - most_common_keys))
        missing_keys = sorted(list(most_common_keys - current_keys))

        unique_combinations.append({
            "combo_id": f"Combo #{rank}",
            "file_count": count,
            "percentage": round(pct, 2),
            "field_count": len(k_set),
            "fields": sorted(list(k_set)),
            "diff_from_primary": {
                "extra_fields": added_keys,
                "missing_fields": missing_keys
            },
            "sample_files": combination_files[k_set][:3]
        })

    # --- 3) Unique list of fields across all files ---
    unique_fields_list = []
    all_unique_keys = sorted(list(all_keys_counter.keys()))

    for k in all_unique_keys:
        count = all_keys_counter[k]
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        unique_fields_list.append({
            "field": k,
            "file_count": count,
            "percentage": round(pct, 2),
            "sample_values": key_sample_values[k]
        })

    # --- 4) Candidates for standardization ---
    standardization_candidates = []

    # Synonym category detection
    for category, syn_list in KNOWN_SYNONYMS.items():
        found_in_scan = {}
        for syn in syn_list:
            if syn in all_keys_counter:
                count = all_keys_counter[syn]
                pct = (count / processed_count) * 100 if processed_count > 0 else 0
                found_in_scan[syn] = {"count": count, "percentage": round(pct, 2)}

        if len(found_in_scan) > 1:
            standardization_candidates.append({
                "type": "Competing Synonyms",
                "category": category,
                "issue": f"Multiple fields used for '{category}' across collection",
                "competing_fields": found_in_scan,
                "recommendation": f"Standardize on primary field '{syn_list[0]}'"
            })
        elif len(found_in_scan) == 1:
            syn, data = list(found_in_scan.items())[0]
            if syn != syn_list[0]:
                standardization_candidates.append({
                    "type": "Non-Standard Key",
                    "category": category,
                    "issue": f"Non-standard key '{syn}' used instead of standard '{syn_list[0]}'",
                    "competing_fields": found_in_scan,
                    "recommendation": f"Migrate '{syn}' to '{syn_list[0]}'"
                })

    # Low occurrence / fragmented field detection
    fragmented_fields = []
    for k, count in all_keys_counter.items():
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        if 0 < pct < 80.0 and k not in ["COMMENT", "HISTORY", "SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "EXTEND"]:
            fragmented_fields.append({"field": k, "percentage": round(pct, 2), "count": count})

    if fragmented_fields:
        fragmented_fields = sorted(fragmented_fields, key=lambda x: x["percentage"])
        standardization_candidates.append({
            "type": "Fragmented / Optional Metadata",
            "category": "Inconsistent Coverage",
            "issue": f"{len(fragmented_fields)} header fields are present in <80% of files",
            "fragmented_fields": fragmented_fields[:15],
            "recommendation": "Ensure acquisition profiles populate optional headers consistently"
        })

    # --- 5) List of FITS editors or publishers ---
    software_publishers = []
    for pub, count in software_counter.most_common():
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        software_publishers.append({
            "publisher": pub,
            "file_count": count,
            "percentage": round(pct, 2)
        })

    return {
        "total_files": total_files,
        "processed_files": processed_count,
        "failed_files": failed_count,
        "common_field_sets": most_common_sets,
        "unique_combinations": unique_combinations,
        "unique_fields_list": unique_fields_list,
        "standardization_candidates": standardization_candidates,
        "software_publishers": software_publishers
    }
