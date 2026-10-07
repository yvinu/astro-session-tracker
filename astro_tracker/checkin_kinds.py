"""Recognise what the files in a working folder are, for check-in.

Pure logic, no I/O. After stacking and post-processing, a working folder
holds the checked-out subs, a great many intermediate files, and a few
things worth keeping: the stacks and finals, and the logs, settings and
project files that say how they were made. These functions sort one
from the other and make first guesses the user can correct.
"""

import os
import re

KIND_IMAGE = "image"
KIND_SIRIL_LOG = "siril-log"
KIND_SIRIL_SCRIPT = "siril-script"
KIND_SIRIL_CONVERSION = "siril-conversion"
KIND_WIZARD_LOG = "wizard-log"
KIND_PIXINSIGHT = "pixinsight"
KIND_PHOTOSHOP = "photoshop"
KIND_ATTACHMENT = "attachment"

IMAGE_EXTENSIONS = (".fit", ".fits", ".fts", ".xisf", ".tif", ".tiff", ".png", ".jpg", ".jpeg")
LINEAR_EXTENSIONS = (".fit", ".fits", ".fts", ".xisf")

MANIFEST_FILE = "astro-manifest.json"

# Siril numbers the files of a sequence with five zero-padded digits and
# prefixes one more tag per processing step (pp_, bkg_, r_ ...).
# Thousands of these are produced and none is an output. Exactly five
# digits, so a result the user named "m31_2026.fits" is not caught.
_SIRIL_SEQUENCE_FILE = re.compile(r"^(?:[a-z]+_)*[a-z]+_\d{5}\.(?:fit|fits|fts)$", re.IGNORECASE)
_FRAMES_BY_EXPOSURE = re.compile(r"(?<![A-Za-z0-9])(\d+)x\d+(?:\.\d+)?s(?:ec)?(?![A-Za-z])", re.IGNORECASE)
_FRAMES_SUFFIX = re.compile(r"_(\d+)f(?:[._]|$)")


def classify(rel_path):
    """Return the kind of a working-folder file, or None if check-in ignores it.

    `rel_path` uses "/" separators, relative to the working folder.
    Unrecognised files come back as "attachment"; whether those are
    uploaded is the caller's choice.
    """
    parts = rel_path.split("/")
    name = parts[-1]
    lower = name.lower()
    ext = os.path.splitext(lower)[1]

    if name.startswith(".") or lower == MANIFEST_FILE or lower.endswith((".part", ".seq", ".tmp")):
        return None
    if any(part.startswith(".") for part in parts[:-1]):
        return None
    if lower.endswith("_conversion.txt"):
        return KIND_SIRIL_CONVERSION
    if "process" in (p.lower() for p in parts[:-1]) or "drizztmp" in (p.lower() for p in parts[:-1]):
        return None
    if _SIRIL_SEQUENCE_FILE.match(name):
        return None

    if ext in IMAGE_EXTENSIONS:
        return KIND_IMAGE
    if "stackingwizard" in lower or "astrowizard" in lower:
        return KIND_WIZARD_LOG
    if ext == ".log":
        return KIND_SIRIL_LOG
    if ext == ".ssf":
        return KIND_SIRIL_SCRIPT
    if ext in (".xpsm", ".xosm", ".pxiproject", ".xdrz", ".xnml"):
        return KIND_PIXINSIGHT
    if ext in (".psd", ".psb"):
        return KIND_PHOTOSHOP
    return KIND_ATTACHMENT


def suggest_run(names_and_kinds):
    """Guess (tool, run kind) for a set of (file name, kind) pairs. Run kind is "stacking" or "post"."""
    names = [name.lower() for name, _kind in names_and_kinds]
    kinds = {kind for _name, kind in names_and_kinds}
    if any("stackingwizard" in n for n in names):
        return "stackingwizard", "stacking"
    if KIND_SIRIL_CONVERSION in kinds or KIND_SIRIL_LOG in kinds or KIND_SIRIL_SCRIPT in kinds:
        return "siril", "stacking"
    if any("astrowizard" in n for n in names):
        return "astrowizard", "post"
    if KIND_PIXINSIGHT in kinds:
        return "pixinsight", "post"
    if KIND_PHOTOSHOP in kinds:
        return "photoshop", "post"
    return "unknown", "post"


STACKING_TOOLS = ("siril", "naztronomy", "stackingwizard", "wbpp", "deepskystacker", "astap")


def run_kind_for_tool(tool):
    """Whether a named tool makes a stacking run or a post-processing run."""
    return "stacking" if str(tool or "").strip().lower() in STACKING_TOOLS else "post"


def guess_frames(name):
    """The frame count a tool wrote into an output's name ("..._302x15sec_...", "..._732f.fits"), or None."""
    match = _FRAMES_BY_EXPOSURE.search(name) or _FRAMES_SUFFIX.search(name)
    return int(match.group(1)) if match else None


def guess_stage(name, run_kind):
    """A first guess at an image's Stage from its name and the kind of run it came from."""
    lower = name.lower()
    ext = os.path.splitext(lower)[1]
    if "starless" in lower:
        return "starless"
    if "starmask" in lower or "stars_only" in lower or "starsonly" in lower:
        return "stars"
    if ext not in LINEAR_EXTENSIONS:
        return "final"
    if "_spcc" in lower or "_pcc" in lower:
        return "stack-cc"
    stem = os.path.splitext(lower)[0]
    if stem.endswith("_og") or "wizardstack" in lower or "_stack" in lower:
        return "stack"
    return "stack" if run_kind == "stacking" else "final"
