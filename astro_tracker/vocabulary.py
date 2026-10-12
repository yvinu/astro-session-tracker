"""The vocabularies every name and grouping is derived from: Rig, Target, Filter, Night, Stage.

Pure logic, no I/O. Devices and capture software each describe the same
things differently -- "IRCUT", "Astro" and "UV/IR" are one filter; "M 8"
and "NGC 6530" one target; two set-ups of the same scope and camera are
two optical configurations. These functions map what the headers say
onto one controlled set of values, which the catalog stores beside the
values read from the file. Files themselves are never rewritten.
"""

import re
from collections import Counter
from datetime import datetime, timedelta
from fnmatch import fnmatchcase

STAGES = ("stack", "stack-cc", "starless", "stars", "final")

MULTI = "multi"
NO_FILTER = "NONE"

RIG_ASSIGNED = "assigned"
RIG_UNASSIGNED = "unassigned"
RIG_AMBIGUOUS = "ambiguous"

# Seed for the filter mapping table; the user edits the table, not this.
DEFAULT_FILTER_MAP = {
    "no filter": NO_FILTER, "none": NO_FILTER, "": NO_FILTER,
    "ircut": "UVIR", "ir cut": "UVIR", "uv/ir": "UVIR", "uvir": "UVIR", "astro": "UVIR", "l": "L", "lum": "L",
    "lp": "LP", "duo-band": "DUO", "dual-band": "DUO", "duo band": "DUO", "dual band": "DUO",
    "r": "R", "g": "G", "b": "B",
    "ha": "Ha", "h-alpha": "Ha", "halpha": "Ha", "oiii": "OIII", "o3": "OIII", "sii": "SII", "s2": "SII",
}

_UNSAFE = re.compile(r"[^A-Za-z0-9.-]+")
_CATALOG_DESIGNATION = re.compile(r"^([A-Za-z]+)\s+(\d+[A-Za-z]?)$")


def slug(value, default="unknown"):
    """Reduce a value to characters that are safe in a file name: letters, digits, dot and hyphen.

    Underscore is excluded on purpose -- it is the field separator in
    canonical names (see canonical_name), so a field must never contain one.
    """
    cleaned = _UNSAFE.sub("-", str(value or "").strip()).strip("-.")
    return cleaned or default


# ---- Rig --------------------------------------------------------------------

def _in_ranges(date, ranges):
    """True if an ISO date (or datetime) string falls in any [start, end] range; open ends are None."""
    if not ranges:
        return True
    if not date or date == "Unknown":
        return False
    day = str(date)[:10]
    return any((start is None or day >= start) and (end is None or day <= end) for start, end in ranges)


# Words in a camera name that say nothing about which camera it is. Capture
# programs disagree on them: "ZWO ASI294MC Pro" and "ZWO CCD ASI294MC Pro"
# are one camera.
_CAMERA_NOISE = {"zwo", "ccd", "cmos", "camera", "qhyccd", "qhy"}


def normalize_camera(instrument):
    """Reduce a camera name to a comparable key: lower case, vendor words and punctuation removed."""
    tokens = re.findall(r"[a-z0-9]+", str(instrument or "").lower())
    kept = [t for t in tokens if t not in _CAMERA_NOISE]
    key = "".join(kept)
    return "" if key in ("", "unknown") else key


def _matches_camera_and_focal(rig, camera, focal):
    if not rig.get("camera") or rig["camera"] != camera:
        return False
    low, high = rig.get("focal_min"), rig.get("focal_max")
    if low is None and high is None:
        return True
    return focal is not None and (low is None or focal >= low) and (high is None or focal <= high)


def assign_rig(optical_train, date, rigs, instrument=None, focal_length=None):
    """Pick the Rig a file belongs to from its camera, measured focal length, Optical Train label and capture date.

    `rigs` is an iterable of dicts. A Rig claims a file in either of two ways:

    - 'camera' with an optional 'focal_min'..'focal_max' range: the
      file's camera (normalize_camera) is the Rig's and its focal length
      is in range. This is the usual way, because the same set-up is
      written many ways -- the focal length in the header is often the
      plate-solved value and differs a little every night, and the
      "telescope" may be the mount's name.
    - 'patterns': shell-style globs matched case-insensitively against
      the whole Optical Train string, for anything the first way cannot
      express.

    'date_ranges' (list of [start, end] ISO dates, either end None; an
    empty list means always) applies to both.

    Returns (rig_id, status). A file matching no Rig is unassigned; one
    matching more than one is ambiguous and gets no Rig, because picking
    one arbitrarily would silently mix two optical configurations.
    """
    train = (optical_train or "").lower()
    camera = normalize_camera(instrument)
    focal = focal_length
    matches = [
        rig["id"] for rig in rigs
        if (any(fnmatchcase(train, p.lower()) for p in rig.get("patterns") or [])
            or _matches_camera_and_focal(rig, camera, focal))
        and _in_ranges(date, rig.get("date_ranges") or [])
    ]
    if len(matches) == 1:
        return matches[0], RIG_ASSIGNED
    return None, RIG_AMBIGUOUS if matches else RIG_UNASSIGNED


def suggest_rigs(trains, tolerance=0.03):
    """Group the library's unassigned Optical Trains into proposed Rigs.

    `trains` are dicts with optical_train, instrument, focal_length,
    file_count, unassigned_count, first_date and last_date. Trains are grouped by
    camera, then by focal length: sorted, with a new group wherever the
    next focal length is more than `tolerance` above the previous one.
    Plate-solved focal lengths for one set-up scatter by a percent or so;
    a reducer or a different scope moves it by far more, so they separate.

    Trains with no recognisable camera or no focal length are left out --
    those need a hand-written pattern.

    Returns proposals, largest first, each with a suggested id and name,
    the camera key, a focal range with a small margin, a nominal focal
    length (the middle measured value by file count, to a whole
    millimetre, for the user to correct to the maker's figure), and the
    trains it covers.
    """
    by_camera = {}
    for train in trains:
        camera = normalize_camera(train.get("instrument"))
        focal = train.get("focal_length")
        if not camera or focal is None or not train.get("unassigned_count"):
            continue
        by_camera.setdefault(camera, []).append((focal, train))

    proposals = []
    for camera, members in by_camera.items():
        members.sort(key=lambda m: m[0])
        clusters = [[members[0]]]
        for member in members[1:]:
            if member[0] > clusters[-1][-1][0] * (1 + tolerance):
                clusters.append([member])
            else:
                clusters[-1].append(member)
        for cluster in clusters:
            focals = [f for f, _t in cluster]
            covered = [t for _f, t in cluster]
            typical = sorted(covered, key=lambda t: -t["file_count"])[0]
            centre = round(_weighted_median([(f, t["unassigned_count"]) for f, t in cluster]))
            margin = tolerance / 3
            dates = [d[:10] for t in covered for d in (t.get("first_date"), t.get("last_date")) if d and d != "Unknown"]
            proposals.append({
                "id": slug(f"{camera}-{centre}mm"),
                "name": typical.get("instrument") or camera,
                "camera": camera,
                "focal_min": round(min(focals) * (1 - margin), 1),
                "focal_max": round(max(focals) * (1 + margin), 1),
                "focal_nominal": float(centre),
                "file_count": sum(t["unassigned_count"] for t in covered),
                "first_date": min(dates) if dates else None,
                "last_date": max(dates) if dates else None,
                "optical_trains": [t["optical_train"] for t in covered],
            })
    return sorted(proposals, key=lambda p: -p["file_count"])


def _weighted_median(pairs):
    """The value at the middle of the total weight, from (value, weight) pairs."""
    ordered = sorted(pairs)
    half = sum(weight for _value, weight in ordered) / 2
    running = 0
    for value, weight in ordered:
        running += weight
        if running >= half:
            return value
    return ordered[-1][0]


# ---- Filter -----------------------------------------------------------------

def filter_key(raw):
    return str(raw or "").strip().lower()


def canonical_filter(raw, mapping):
    """Map a header filter value to its canonical name; unmapped values pass through, made name-safe."""
    key = filter_key(raw)
    if key in mapping:
        return mapping[key]
    return slug(raw, NO_FILTER)


# ---- Target -----------------------------------------------------------------

def default_target_name(labels):
    """Derive a canonical Target name from a target group's OBJECT labels.

    Takes the most common real label and makes it name-safe, closing the
    gap in catalogue designations ("M 8" -> "M8", "NGC 7380" -> "NGC7380").
    `labels` may repeat; pass one entry per file for a true majority.
    """
    counts = Counter(l.strip() for l in labels if l and l.strip() and l.strip() != "Unknown")
    if not counts:
        return "unknown"
    label = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    match = _CATALOG_DESIGNATION.match(label)
    if match:
        return match.group(1) + match.group(2)
    return slug(label)


def unique_name(name, taken):
    """Return `name`, or `name-2`, `name-3`... if it is already in `taken`."""
    if name not in taken:
        return name
    n = 2
    while f"{name}-{n}" in taken:
        n += 1
    return f"{name}-{n}"


# ---- Night ------------------------------------------------------------------

NIGHT_BOUNDARY_HOUR = 12


def _parse(date_obs):
    if not date_obs or date_obs == "Unknown":
        return None
    text = str(date_obs).strip()
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def corrected_utc(date_obs, exposure=0, correction=None):
    """Turn a header timestamp into the UTC start of the exposure.

    `correction` describes what a Source's headers actually mean:
      utc_offset_hours  the header is local time this many hours ahead of UTC
      marks             "start" (default) or "end" of the exposure

    With no correction the header is taken as UTC start, which is what
    most capture software writes. Returns an ISO string, or None if the
    header cannot be parsed.
    """
    dt = _parse(date_obs)
    if dt is None:
        return None
    correction = correction or {}
    dt -= timedelta(hours=correction.get("utc_offset_hours", 0))
    if correction.get("marks") == "end":
        dt -= timedelta(seconds=float(exposure or 0))
    return dt.isoformat()


def observation_night(utc_start, site_utc_offset_hours=0):
    """The Night an exposure belongs to: the local date of the dusk it followed.

    Local noon is the boundary, so everything from one afternoon to the
    next morning is one Night. With no site offset this is the same
    UTC-noon rule sessions.derive_observation_night has always used.
    """
    dt = _parse(utc_start)
    if dt is None:
        return "Unknown"
    local = dt + timedelta(hours=site_utc_offset_hours)
    return (local - timedelta(hours=NIGHT_BOUNDARY_HOUR)).date().isoformat()


# ---- Canonical names --------------------------------------------------------

def _format_exposure(exposure):
    value = float(exposure or 0)
    return f"{value:g}"


def one_or_multi(values):
    """The single distinct value in `values`, or "multi" when there is more than one."""
    distinct = {v for v in values if v}
    return distinct.pop() if len(distinct) == 1 else MULTI if distinct else "unknown"


def canonical_name(target, rig, filter_name, stage, frames, exposure, version, ext):
    """Build the stored name of a stack or final image.

    <target>_<rig>_<filter>_<stage>_<frames>x<exposure>s_v<NN>.<ext>

    Underscores separate the fields and never appear inside one, so the
    name can be split back into its parts.
    """
    if stage not in STAGES:
        raise ValueError(f"Unknown stage '{stage}'; expected one of {', '.join(STAGES)}")
    parts = [
        slug(target), slug(rig), slug(filter_name), stage,
        f"{int(frames or 0)}x{_format_exposure(exposure)}s",
        f"v{int(version):02d}",
    ]
    return "_".join(parts) + "." + str(ext).lstrip(".").lower()
