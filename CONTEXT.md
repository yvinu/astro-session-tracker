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
_Avoid_: Hash, checksum (the fingerprint involves no content hashing; see Content Hash for the one that does)

**Content Hash**:
The SHA-256 of a File's bytes, computed on the NAS in a background pass and stored with the size and modification time it was computed at. Two Files with the same Content Hash are exactly the same file. Required before anything is deleted on the strength of another copy existing; the Duplicate Fingerprint alone is never enough for that.
_Avoid_: Fingerprint (that is the header-based one), checksum

**Location**:
The physical drive or share a File lives on, derived from its path: the name of the configured library root it sits under (how the service on the NAS names Locations), else the mount segment (`/Volumes/<name>` on macOS), else "Internal" for paths under the boot volume — a property of where the file *is*, not which scan run found it. Covers directly-attached external drives and NAS shares alike.
_Avoid_: Drive (fine informally, but "Location" is the stored/filterable term), Scan directory (that's the scan-time input, not the file's location)

The NAS Location is canonical for duplicate consolidation — see [ADR-0003](docs/adr/0003-nas-is-canonical-location.md).

**Resolution**:
A File's pixel dimensions, formatted as `NAXIS1`x`NAXIS2` (e.g. `"5496x3672"`), read from the FITS/XISF header.

**Binning**:
Sensor binning (`XBINNING`/`YBINNING`), tracked as its own filterable field alongside Resolution rather than only being implicit in it.

**Source**:
A device that files are pulled from on a schedule (a smart telescope, or the ASIAIR), with its share path, its Mirror folder and its pull interval. Each pull is recorded as a run, whether it copied files, found nothing new, or found the device switched off.
_Avoid_: Device (a Source is the configured thing, not the hardware), remote

**Mirror**:
A Source's permanent folder on the NAS, holding an unedited copy of what is on the device with the device's own folder structure, file names and file dates. A pull adds what the Mirror is missing and never overwrites, renames, moves or deletes. The Mirror is the raw store -- see [ADR-0005](docs/adr/0005-raw-store-is-a-per-source-mirror.md).
_Avoid_: Landing folder (a Mirror is not emptied), archive

**Device Stack**:
A stacked image a smart telescope produced itself, pulled into the Mirror alongside the subs. A File category of its own, apart from Subframe and from Processed files the user made.

**Rig**:
A named optical configuration (e.g. `s50`, `80ed-533mc-r08`), registered by the user with Optical Train patterns and, optionally, the dates it was in use. Each File is assigned to at most one Rig; a File matching none is unassigned and one matching several is ambiguous, never guessed. Adding a reducer or changing the camera makes a new Rig, because flats and image scale change. The Rig, not the Optical Train, is what names and grouping use.
_Avoid_: Setup, configuration, Optical Train (that is the raw value a Rig is matched against)

**Target**:
The canonical name of a target group (e.g. `M8`), unique and name-safe, with aliases. Defaults to the group's most common `OBJECT` label and can be edited; it stays attached to the group across re-clustering.
_Avoid_: Object (that is the raw header label, which is inconsistent)

**Filter**:
The canonical name of a filter (e.g. `UVIR`, `DUO`, `Ha`), mapped from whatever each device writes in its header. Stored beside the header value, which is kept.

**Night**:
The local date of the dusk an exposure followed, computed from corrected UTC with local noon as the boundary. A Source whose headers are not UTC start-of-exposure declares a correction.
_Avoid_: Date (ambiguous across midnight)

**Project**:
One piece of processing work on a Target: it owns its Checkouts and, once work comes back, its runs, stacks and finals. A Target can have several Projects.
_Avoid_: Job, session (a session is a night of capture)

**Checkout**:
One hand-out of subs for a Project, fixed when it is created. Its manifest lists every sub with its Content Hash, grouped by Rig and Filter, each with its position in the order Siril numbers files. A changed selection makes a new Checkout; an existing one is never edited.
_Avoid_: Export, copy

**Stage**:
What an output image is, from a fixed list: `stack`, `stack-cc`, `starless`, `stars`, `final`.

**Canonical Name**:
The stored name of a stack or final: `<target>_<rig>_<filter>_<stage>_<frames>x<exposure>s_v<NN>.<ext>`. Fields are separated by underscores and never contain one. The name a tool gave the file is kept in the catalog. Raw captures are never renamed.

**Optical Train**:
A File's equipment combination, auto-derived from `TELESCOP` + `INSTRUME` + `FOCALLEN` (whatever subset is present; "Unknown" only when all three are missing). Friendly aliasing on top of the raw derived key is deferred to a future release.
_Avoid_: Rig, setup (informal synonyms; "Optical Train" is the stored/filterable term)

