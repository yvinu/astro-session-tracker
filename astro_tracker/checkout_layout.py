"""Where a Checkout's subs go in the Mac working folder, for a given stacking tool.

Pure logic, no I/O. Each stacking tool expects its input laid out its
own way, so the layout is chosen by a named profile at checkout time.
The manifest decides *what* is handed out; the profile only decides
*where it is put*.

naztronomy -- the Naztronomy Smart Telescope Preprocessing script for
Siril reads a flat `lights/` folder directly under Siril's working
directory. A Checkout with one Rig and Filter therefore gets a single
`lights/`. With several, each gets its own subfolder holding a
`lights/`, so frames from different optical configurations or filters
are never linked into one Siril sequence; the user points Siril at each
subfolder in turn.
"""

from astro_tracker import vocabulary

PROFILES = ("naztronomy",)
DEFAULT_PROFILE = "naztronomy"
LIGHTS_DIR = "lights"


def plan_layout(stored_manifest, profile=DEFAULT_PROFILE):
    """Return, per manifest group, the folder (relative to the working folder) its subs are copied into.

    [{"key": ..., "rig": ..., "filter": ..., "lights_dir": "lights", "entries": [...]}, ...]
    """
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile '{profile}'; expected one of {', '.join(PROFILES)}")
    groups = stored_manifest["groups"]
    single = len(groups) == 1
    plan = []
    for group in groups:
        if single:
            lights_dir = LIGHTS_DIR
        else:
            lights_dir = f"{vocabulary.slug(group['rig'])}_{vocabulary.slug(group['filter'])}/{LIGHTS_DIR}"
        plan.append({
            "key": group["key"], "rig": group["rig"], "filter": group["filter"],
            "lights_dir": lights_dir, "entries": group["entries"],
        })
    return plan


def working_folder_name(stored_manifest):
    """Name of the working folder for a Checkout's Project: <target>__<project>."""
    project = stored_manifest["project"]
    return f"{vocabulary.slug(project['target_name'])}__{project['slug']}"
