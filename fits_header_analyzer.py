#!/usr/bin/env python3
"""FITS Header Analyzer Script.

Scans a directory recursively for FITS (and XISF) files, extracts header cards,
and performs statistical analysis to answer 5 key questions:
1) Most common set of fields/cards included across files.
2) Unique combinations of FITS fields seen in a given file.
3) Unique master list of fields seen across all files.
4) Candidates for standardization (competing synonyms & fragmented custom fields).
5) List of FITS editors or publishers that have written the files.

Outputs terminal summary, Markdown report, and JSON report.
"""

import os
import sys
import json
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from astropy.io import fits

try:
    import xisf
    XISF_AVAILABLE = True
except ImportError:
    XISF_AVAILABLE = False

# Basic structural cards to exclude when calculating metadata field combinations
STRUCTURAL_CARDS = {
    "SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "EXTEND", "END",
    "PCOUNT", "GCOUNT", "XTENSION"
}

# Key synonyms for standardization mapping
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

DEFAULT_SCAN_DIR = "/Users/yvinu/Documents/AP"
DEFAULT_MD_REPORT = "FITS_Header_Analysis.md"
DEFAULT_JSON_REPORT = "fits_header_analysis.json"


def extract_header(file_path):
    """Extract all header keys and sample values from a FITS or XISF file."""
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
            
            # Select HDU: fallback to HDU 1 if Primary HDU has no image cards/payload
            selected_hdu = hdul[0]
            if len(hdul) > 1 and selected_hdu.header.get('NAXIS', 0) == 0:
                selected_hdu = hdul[1]

            header = selected_hdu.header
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
    """Identify software editors or publishers from header fields or comments."""
    publishers = set()

    sw_cards = ["SWCREATE", "CREATOR", "PROGRAM", "SOFTWARE", "ORIGIN"]
    for card in sw_cards:
        val = header_data.get(card, "")
        if val and val != "Unknown":
            publishers.add(val.strip())

    ext = os.path.splitext(file_path)[1].lower()
    if ext in [".fits", ".fit", ".fts"]:
        try:
            with fits.open(file_path, mode='readonly', ignore_missing_end=True) as hdul:
                if len(hdul) > 0:
                    header = hdul[0].header
                    history_list = header.get('HISTORY', [])
                    comment_list = header.get('COMMENT', [])
                    
                    history_str = " ".join([str(c) for c in history_list]) if isinstance(history_list, (list, fits.header._HeaderCommentaryCards)) else str(history_list)
                    comment_str = " ".join([str(c) for c in comment_list]) if isinstance(comment_list, (list, fits.header._HeaderCommentaryCards)) else str(comment_list)
                    
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


def run_analysis(scan_directory, ignore_symlinks=True, min_combo_pct=1.0, progress_callback=None):
    """Perform recursive scanning and statistical analysis on FITS headers."""
    files_to_scan = []
    symlink_count = 0

    for root, dirs, files in os.walk(scan_directory):
        for file in files:
            if file.lower().endswith(('.fits', '.fit', '.fts', '.xisf')):
                full_path = os.path.join(root, file)
                if os.path.islink(full_path):
                    symlink_count += 1
                    if ignore_symlinks:
                        continue
                files_to_scan.append(full_path)

    total_files = len(files_to_scan)
    if total_files == 0:
        print(f"⚠️  No FITS/XISF files found in '{scan_directory}'.")
        return None

    if symlink_count > 0:
        if ignore_symlinks:
            print(f"🔍 Found {total_files} file(s) ({symlink_count} symbolic link(s) ignored by default). Analyzing FITS headers...\n")
        else:
            print(f"🔍 Found {total_files} file(s) (including {symlink_count} symbolic link(s)). Analyzing FITS headers...\n")
    else:
        print(f"🔍 Found {total_files} file(s). Analyzing FITS headers...\n")

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

        if idx % 20 == 0 or idx == total_files:
            progress = (idx / total_files) * 100
            print(f"Processing: {idx}/{total_files} ({progress:.1f}%)", end='\r')

        header_data = extract_header(file_path)
        if not header_data:
            failed_count += 1
            continue

        processed_count += 1

        # All keys vs metadata keys (excluding structural)
        all_keys = set(header_data.keys())
        meta_keys = tuple(sorted(all_keys - STRUCTURAL_CARDS))
        meta_key_set = frozenset(meta_keys)

        key_set_counter[meta_key_set] += 1
        combination_files[meta_key_set].append(os.path.basename(file_path))

        for k, v in header_data.items():
            all_keys_counter[k] += 1
            if v and len(key_sample_values[k]) < 5:
                if v not in key_sample_values[k]:
                    key_sample_values[k].append(v)

        pubs = extract_software_publishers(file_path, header_data)
        for p in pubs:
            software_counter[p] += 1

    print("\n✅ Header processing complete!\n")

    # --- Q1: Most Common Set of Fields/Cards ---
    all_common_sets = []
    total_signatures = len(key_set_counter)

    for rank, (k_set, count) in enumerate(key_set_counter.most_common(), 1):
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        all_common_sets.append({
            "rank": rank,
            "field_count": len(k_set),
            "file_count": count,
            "percentage": round(pct, 2),
            "fields": sorted(list(k_set))
        })

    common_sets = [cs for cs in all_common_sets if cs["percentage"] >= min_combo_pct]

    # Calculate rare signature totals
    rare_sets = [cs for cs in all_common_sets if cs["percentage"] < min_combo_pct]
    rare_file_count = sum(cs["file_count"] for cs in rare_sets)
    rare_pct = round((rare_file_count / processed_count) * 100, 2) if processed_count > 0 else 0

    # --- Q2: Unique Combinations of FITS Fields ---
    unique_combinations = []
    primary_keys = set(all_common_sets[0]["fields"]) if all_common_sets else set()

    for rank, (k_set, count) in enumerate(key_set_counter.most_common(), 1):
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        if min_combo_pct > 0 and pct < min_combo_pct:
            continue

        current_keys = set(k_set)
        added_keys = sorted(list(current_keys - primary_keys))
        missing_keys = sorted(list(primary_keys - current_keys))

        unique_combinations.append({
            "combo_id": f"Signature #{rank}",
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

    # --- Q3: Unique Master List of Fields ---
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

    # --- Q4: Candidates for Standardization ---
    standardization_candidates = []

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
                "issue": f"Multiple fields used for '{category}' across dataset",
                "competing_fields": found_in_scan,
                "recommendation": f"Standardize on primary keyword '{syn_list[0]}'"
            })
        elif len(found_in_scan) == 1:
            syn = list(found_in_scan.keys())[0]
            if syn != syn_list[0]:
                standardization_candidates.append({
                    "type": "Non-Standard Keyword",
                    "category": category,
                    "issue": f"Non-standard key '{syn}' used instead of '{syn_list[0]}'",
                    "competing_fields": found_in_scan,
                    "recommendation": f"Migrate '{syn}' to standard '{syn_list[0]}'"
                })

    # Fragmented optional fields (<80% coverage)
    fragmented_fields = []
    for k, count in all_keys_counter.items():
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        if 0 < pct < 80.0 and k not in STRUCTURAL_CARDS and k not in ["COMMENT", "HISTORY"]:
            fragmented_fields.append({"field": k, "percentage": round(pct, 2), "count": count})

    if fragmented_fields:
        fragmented_fields = sorted(fragmented_fields, key=lambda x: x["percentage"])
        standardization_candidates.append({
            "type": "Fragmented / Optional Metadata",
            "category": "Inconsistent Coverage",
            "issue": f"{len(fragmented_fields)} header fields appear in <80% of files",
            "fragmented_fields": fragmented_fields,
            "recommendation": "Configure acquisition tools to write optional headers consistently"
        })

    # --- Q5: List of Software Editors or Publishers ---
    software_publishers = []
    for pub, count in software_counter.most_common():
        pct = (count / processed_count) * 100 if processed_count > 0 else 0
        software_publishers.append({
            "publisher": pub,
            "file_count": count,
            "percentage": round(pct, 2)
        })

    return {
        "scan_directory": scan_directory,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": total_files,
        "symlink_count": symlink_count,
        "processed_files": processed_count,
        "failed_files": failed_count,
        "total_signatures": total_signatures,
        "min_combo_pct": min_combo_pct,
        "rare_signature_count": len(rare_sets),
        "rare_file_count": rare_file_count,
        "rare_pct": rare_pct,
        "common_field_sets": common_sets,
        "unique_combinations": unique_combinations,
        "unique_fields_list": unique_fields_list,
        "standardization_candidates": standardization_candidates,
        "software_publishers": software_publishers
    }


def print_terminal_report(results):
    """Print clean terminal report answering all 5 questions."""
    print("=" * 80)
    print(" 🌌 FITS HEADER ANALYSIS SUMMARY")
    print("=" * 80)
    print(f" Directory: {results['scan_directory']}")
    symlink_info = f" (including {results['symlink_count']} symlinks)" if results.get('symlink_count', 0) > 0 else ""
    print(f" Files Found: {results['total_files']}{symlink_info} | Processed: {results['processed_files']} | Failed: {results['failed_files']}")
    print("-" * 80)

    # Question 1
    print("\n1️⃣  MOST COMMON SET OF FIELDS / CARDS")
    for cs in results['common_field_sets'][:5]:
        print(f"   Rank #{cs['rank']}: {cs['file_count']} file(s) ({cs['percentage']}%) - {cs['field_count']} metadata fields")
        print(f"      Fields: {', '.join(cs['fields'][:12])}{'...' if len(cs['fields']) > 12 else ''}")

    # Question 2
    print("\n2️⃣  UNIQUE COMBINATIONS OF FITS FIELDS")
    total_sig = results.get('total_signatures', len(results['unique_combinations']))
    min_pct = results.get('min_combo_pct', 0)
    rare_count = results.get('rare_signature_count', 0)
    rare_files = results.get('rare_file_count', 0)
    rare_pct = results.get('rare_pct', 0)

    print(f"   Total Unique Signatures: {total_sig} | Displaying Signatures >= {min_pct}%")
    if rare_count > 0:
        print(f"   (Excluded {rare_count} rare signatures [< {min_pct}%], representing {rare_files} files / {rare_pct}% of dataset)")

    for uc in results['unique_combinations']:
        diff_str = ""
        if uc['diff_from_primary']['extra_fields']:
            diff_str += f" +Extra: {', '.join(uc['diff_from_primary']['extra_fields'])}"
        if uc['diff_from_primary']['missing_fields']:
            diff_str += f" -Missing: {', '.join(uc['diff_from_primary']['missing_fields'])}"
        if not diff_str:
            diff_str = " (Primary Signature)"
        print(f"   {uc['combo_id']}: {uc['file_count']} file(s) ({uc['percentage']}%) - {uc['field_count']} fields{diff_str}")

    # Question 3
    print("\n3️⃣  UNIQUE MASTER LIST OF FIELDS ACROSS ALL FILES")
    print(f"   Total Unique Header Fields: {len(results['unique_fields_list'])}")
    all_fields_str = ", ".join([f["field"] for f in results['unique_fields_list']])
    print(f"   Fields: {all_fields_str[:120]}...")

    # Question 4
    print("\n4️⃣  CANDIDATES FOR STANDARDIZATION")
    for cand in results['standardization_candidates']:
        print(f"   • [{cand['type']}] {cand['category']}: {cand['issue']}")
        if "competing_fields" in cand:
            fields_detail = ", ".join([f"{k} ({v['percentage']}%)" for k, v in cand['competing_fields'].items()])
            print(f"     Competing: {fields_detail}")
        print(f"     👉 Rec: {cand['recommendation']}")

    # Question 5
    print("\n5️⃣  FITS EDITORS / PUBLISHERS DETECTED")
    for pub in results['software_publishers']:
        print(f"   • {pub['publisher']}: {pub['file_count']} file(s) ({pub['percentage']}%)")
    print("=" * 80 + "\n")


def generate_markdown_report(results, output_file):
    """Write comprehensive GitHub-Flavored Markdown report."""
    md = []
    md.append(f"# FITS Header Analysis Report\n")
    md.append(f"- **Scan Directory**: `{results['scan_directory']}`")
    md.append(f"- **Timestamp**: {results['timestamp']}")
    md.append(f"- **Total Files Found**: {results['total_files']} (Symlinks: {results.get('symlink_count', 0)})")
    md.append(f"- **Successfully Processed**: {results['processed_files']}")
    md.append(f"- **Failed Files**: {results['failed_files']}\n")

    # Q1
    md.append("## 1. Most Common Set of Fields / Cards\n")
    md.append(f"The table below shows header key-sets appearing in >= {results.get('min_combo_pct', 1.0)}% of scanned files:\n")
    md.append("| Rank | Files | Coverage | Field Count | Common Header Fields |")
    md.append("|---|---|---|---|---|")
    for cs in results['common_field_sets']:
        fields_snippet = ", ".join(cs['fields'][:10])
        if len(cs['fields']) > 10:
            fields_snippet += "..."
        md.append(f"| {cs['rank']} | {cs['file_count']} | {cs['percentage']}% | {cs['field_count']} | `{fields_snippet}` |")
    md.append("\n")

    # Q2
    md.append("## 2. Unique Combinations of FITS Fields\n")
    total_sig = results.get('total_signatures', len(results['unique_combinations']))
    min_pct = results.get('min_combo_pct', 0)
    rare_count = results.get('rare_signature_count', 0)
    rare_files = results.get('rare_file_count', 0)
    rare_pct = results.get('rare_pct', 0)

    md.append(f"Discovered **{total_sig} total distinct field signatures**.")
    if rare_count > 0:
        md.append(f" *(Excluded {rare_count} rare signatures [< {min_pct}%], representing {rare_files} files / {rare_pct}% of collection)*:\n")
    else:
        md.append("\n")

    for uc in results['unique_combinations']:
        md.append(f"### {uc['combo_id']} ({uc['file_count']} files, {uc['percentage']}%)")
        md.append(f"- **Field Count**: {uc['field_count']}")
        md.append(f"- **Sample Files**: `{', '.join(uc['sample_files'])}`")
        if uc['diff_from_primary']['extra_fields']:
            md.append(f"- **Extra Fields vs Primary**: `{', '.join(uc['diff_from_primary']['extra_fields'])}`")
        if uc['diff_from_primary']['missing_fields']:
            md.append(f"- **Missing Fields vs Primary**: `{', '.join(uc['diff_from_primary']['missing_fields'])}`")
        md.append(f"- **Complete Key Set**: `{', '.join(uc['fields'])}`\n")

    # Q3
    md.append("## 3. Master List of Fields Across All Files\n")
    md.append(f"Total **{len(results['unique_fields_list'])} unique header keywords** identified across all files:\n")
    md.append("| Field Name | Occurrence Count | Coverage | Sample Values |")
    md.append("|---|---|---|---|")
    for uf in results['unique_fields_list']:
        samples = ", ".join([str(v) for v in uf['sample_values'][:3]])
        md.append(f"| `{uf['field']}` | {uf['file_count']} | {uf['percentage']}% | `{samples}` |")
    md.append("\n")

    # Q4
    md.append("## 4. Candidates for Standardization\n")
    for cand in results['standardization_candidates']:
        md.append(f"### {cand['category']} ({cand['type']})")
        md.append(f"- **Issue**: {cand['issue']}")
        if "competing_fields" in cand:
            comp_str = ", ".join([f"`{k}` ({v['percentage']}%)" for k, v in cand['competing_fields'].items()])
            md.append(f"- **Competing Fields**: {comp_str}")
        md.append(f"- **Recommendation**: {cand['recommendation']}\n")

    # Q5
    md.append("## 5. FITS Editors and Publishers\n")
    md.append("| Software / Publisher Signature | File Count | Coverage |")
    md.append("|---|---|---|")
    for pub in results['software_publishers']:
        md.append(f"| {pub['publisher']} | {pub['file_count']} | {pub['percentage']}% |")
    md.append("\n")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(md))
    print(f"📄 Saved Markdown report to: {output_file}")


def generate_json_report(results, output_file):
    """Write structured JSON report."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f"📊 Saved JSON report to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="FITS Header Analyzer - Analyze field combinations, software origins, and standardization opportunities.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-d', '--directory', default=DEFAULT_SCAN_DIR, help=f"Directory to scan (default: {DEFAULT_SCAN_DIR})")
    parser.add_argument('-o', '--output-md', default=DEFAULT_MD_REPORT, help=f"Markdown report path (default: {DEFAULT_MD_REPORT})")
    parser.add_argument('-j', '--output-json', default=DEFAULT_JSON_REPORT, help=f"JSON report path (default: {DEFAULT_JSON_REPORT})")
    parser.add_argument('--include-symlinks', action='store_true', help="Include symbolic link files in header analysis (ignored by default).")
    parser.add_argument('--min-combo-pct', type=float, default=1.0, help="Minimum percentage threshold (0.0 to 100.0) for displaying unique field combinations (default: 1.0).")

    args = parser.parse_args()

    scan_dir = os.path.expanduser(args.directory)
    if not os.path.exists(scan_dir):
        print(f"❌ Error: Directory '{scan_dir}' does not exist.")
        sys.exit(1)

    results = run_analysis(scan_dir, ignore_symlinks=not args.include_symlinks, min_combo_pct=args.min_combo_pct)
    if results:
        print_terminal_report(results)
        generate_markdown_report(results, args.output_md)
        generate_json_report(results, args.output_json)


if __name__ == "__main__":
    main()

