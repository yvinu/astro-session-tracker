# Astro Session Tracker

Domain vocabulary for the FITS/XISF inventory tracker: a single-user, local-first tool that scans astrophotography libraries into SQLite and groups them into sessions and target groups.

## Language

**File**:
One row in `files`, keyed by absolute `path`. Represents one physical copy of a FITS/XISF file at one location on disk — the same content stored in two places (e.g. two drives) is two Files.
_Avoid_: Sub, frame (those describe the file's *role* — see Frame Type — not its identity)

**Duplicate Group**:
A set of Files whose content is the same, regardless of path or drive. Membership is a derived/computed relationship between Files, not a replacement for File identity — deduplication never merges File rows.
_Avoid_: Copy set

**Duplicate Fingerprint**:
The tuple (size, DATE-OBS, EXPTIME, OBJECT, INSTRUME) used to recognize that two Files are the same exposure, without reading file contents. See [ADR-0001](docs/adr/0001-metadata-fingerprint-for-duplicate-detection.md).
_Avoid_: Hash, checksum (no content hashing is involved)

**Location**:
The physical drive or share a File lives on, derived from its path's mount segment (`/Volumes/<name>` on macOS, or "Internal" for paths under the boot volume) — a property of where the file *is*, not which scan run found it. Covers directly-attached external drives and NAS shares alike.
_Avoid_: Drive (fine informally, but "Location" is the stored/filterable term), Scan directory (that's the scan-time input, not the file's location)

The NAS Location is canonical for duplicate consolidation — see [ADR-0003](docs/adr/0003-nas-is-canonical-location.md).

**Resolution**:
A File's pixel dimensions, formatted as `NAXIS1`x`NAXIS2` (e.g. `"5496x3672"`), read from the FITS/XISF header.

**Binning**:
Sensor binning (`XBINNING`/`YBINNING`), tracked as its own filterable field alongside Resolution rather than only being implicit in it.

**Optical Train**:
A File's equipment combination, auto-derived from `TELESCOP` + `INSTRUME` + `FOCALLEN` (whatever subset is present; "Unknown" only when all three are missing). Friendly aliasing on top of the raw derived key is deferred to a future release.
_Avoid_: Rig, setup (informal synonyms; "Optical Train" is the stored/filterable term)

