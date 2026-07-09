"""RA/DEC-based field-of-view clustering.

Groups files by actual sky position (great-circle proximity) rather than
by the OBJECT header string, so a mislabeled or inconsistently-named
target is still recognized as the same integration project.

Pure logic, no I/O — the caller is responsible for loading file records
and persisting the resulting group assignments.
"""

import math

DEFAULT_TOLERANCE_DEG = 1.0  # sized to the Seestar's ~1 degree field of view


def angular_separation_deg(ra1, dec1, ra2, dec2):
    """Great-circle angular separation between two RA/DEC points, in degrees.

    RA/DEC are expected in decimal degrees.
    """
    ra1_r, dec1_r, ra2_r, dec2_r = (math.radians(v) for v in (ra1, dec1, ra2, dec2))
    cos_sep = (
        math.sin(dec1_r) * math.sin(dec2_r)
        + math.cos(dec1_r) * math.cos(dec2_r) * math.cos(ra1_r - ra2_r)
    )
    # Guard against floating-point drift pushing slightly outside [-1, 1]
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep))


def _parse_coord(value):
    """Parse a raw header RA/DEC value to a float. Returns None if missing/malformed.

    Only decimal-degree values are supported in v1; sexagesimal strings
    (e.g. "05:34:32") are treated as malformed and left ungrouped rather
    than crashing the run.
    """
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


class _UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self.parent[root_a] = root_b


def cluster_files(files, tolerance_deg=DEFAULT_TOLERANCE_DEG):
    """Group files by RA/DEC proximity.

    `files` is an iterable of dicts, each with an 'id' key (any hashable
    identifier) and 'ra'/'dec' keys holding raw header values (which may
    be None, numeric, or a malformed string).

    Two files land in the same group if there's a chain of pairwise
    separations, each <= tolerance_deg, connecting them (transitive
    clustering, not simple nearest-centroid).

    Returns a dict mapping each file's id to a zero-based group id.
    Files with missing/malformed coordinates map to None (ungrouped)
    rather than being merged into any group or raising an error.

    Note: this does a pairwise O(n^2) comparison across all files with
    usable coordinates. Fine for a personal library's distinct-pointing
    count; a spatial index would be the next step if that ever becomes
    a bottleneck.
    """
    files = list(files)
    coords = {}
    for f in files:
        ra = _parse_coord(f.get("ra"))
        dec = _parse_coord(f.get("dec"))
        coords[f["id"]] = (ra, dec) if (ra is not None and dec is not None) else None

    valid_ids = [f["id"] for f in files if coords[f["id"]] is not None]
    index_of = {fid: i for i, fid in enumerate(valid_ids)}
    uf = _UnionFind(len(valid_ids))

    for i in range(len(valid_ids)):
        ra1, dec1 = coords[valid_ids[i]]
        for j in range(i + 1, len(valid_ids)):
            ra2, dec2 = coords[valid_ids[j]]
            if angular_separation_deg(ra1, dec1, ra2, dec2) <= tolerance_deg:
                uf.union(i, j)

    root_to_group = {}
    group_of = {}
    next_group_id = 0
    for fid in valid_ids:
        root = uf.find(index_of[fid])
        if root not in root_to_group:
            root_to_group[root] = next_group_id
            next_group_id += 1
        group_of[fid] = root_to_group[root]

    for f in files:
        group_of.setdefault(f["id"], None)

    return group_of
