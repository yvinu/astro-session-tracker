"""Plan a Siril-shaped Lights export for a target group.

Rather than symlinking files in place (fragile when the source lives on
a NAS/network volume that may not be mounted, and incompatible with
Siril's debayer-on-convert step), this generates a standalone shell
script that copies the group's Light frames into a flat `lights/`
folder -- the layout Siril scripting tools (e.g. Naztronomy's
preprocessing script) expect directly under the working directory.

The script is written to disk but never run automatically: the source
volume may not be mounted at export time, and the user should be able
to review/run it (and re-run it later) on their own schedule.

Frames from different camera/filter combinations are never copied into
the same lights/ folder -- each combination gets its own subfolder so a
Siril run never mixes incompatible frames. Pure filesystem/string
logic, no DB access -- the caller loads the group's file records and
passes them in.
"""

import os
import re
import shlex
from collections import Counter, defaultdict

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize(value, default):
    if not value:
        return default
    cleaned = _UNSAFE_CHARS.sub("_", str(value).strip())
    return cleaned or default


def _pick_group_label(files):
    """Most common non-empty, non-"Unknown" target label, for naming the working folder."""
    counts = Counter(f["target"] for f in files if f.get("target") and f["target"] != "Unknown")
    if not counts:
        return "target"
    return counts.most_common(1)[0][0]


def _camera_label(f):
    value = f.get("optical_train")
    if not value or value == "Unknown":
        value = f.get("instrument")
    if not value or value == "Unknown":
        value = None
    return _sanitize(value, "UnknownCamera")


def _volume_root(path):
    """Return the `/Volumes/<name>` mount-point prefix of `path`, or None if it isn't under one."""
    parts = path.split(os.sep)
    if len(parts) >= 3 and parts[1] == "Volumes" and parts[2]:
        return os.sep.join(parts[:3])
    return None


def build_lights_export(files, destination_root, group_id):
    """Set up a Lights-only export for `files` under `destination_root`.

    `files` is an iterable of dicts with 'path', 'frame_type', 'filter',
    'target', and optionally 'optical_train'/'instrument' keys. Only
    entries with frame_type == "Light" are considered.

    Creates, immediately and idempotently (existing contents are never
    touched or deleted):

        <destination_root>/<label>_group<id>/lights/                       (single camera+filter)
        <destination_root>/<label>_group<id>/<camera>_<filter>/lights/     (multiple camera+filter combos)

    and a `copy_lights.sh` script alongside them that performs the actual
    copy from source when the user runs it later.

    Returns a summary dict: destination, script_path, combos (per
    camera/filter breakdown with lights_dir + count), total_files.
    """
    lights = [f for f in files if f.get("frame_type") == "Light"]
    if not lights:
        return {"destination": None, "script_path": None, "combos": [], "total_files": 0}

    group_label = _sanitize(_pick_group_label(lights), "target")
    group_folder = os.path.join(destination_root, f"{group_label}_group{group_id}")

    by_combo = defaultdict(list)
    for f in lights:
        camera = _camera_label(f)
        filt = _sanitize(f.get("filter"), "NoFilter")
        by_combo[(camera, filt)].append(f)

    single_combo = len(by_combo) == 1

    combos = []
    jobs = []  # (src_path, lights_dir)
    for (camera, filt), combo_files in sorted(by_combo.items()):
        if single_combo:
            lights_dir = os.path.join(group_folder, "lights")
        else:
            lights_dir = os.path.join(group_folder, f"{camera}_{filt}", "lights")
        os.makedirs(lights_dir, exist_ok=True)

        for f in combo_files:
            jobs.append((f["path"], lights_dir))

        combos.append({
            "camera": camera,
            "filter": filt,
            "lights_dir": lights_dir,
            "count": len(combo_files),
        })

    volume_roots = sorted({r for r in (_volume_root(src) for src, _ in jobs) if r})

    script_path = os.path.join(group_folder, "copy_lights.sh")
    with open(script_path, "w") as fh:
        fh.write(_render_script(group_id, jobs, volume_roots))
    os.chmod(script_path, 0o755)

    return {
        "destination": group_folder,
        "script_path": script_path,
        "combos": combos,
        "total_files": len(jobs),
    }


def _render_script(group_id, jobs, volume_roots):
    def quoted_lines(values):
        return "\n".join(f"    {shlex.quote(v)}" for v in values)

    return SCRIPT_TEMPLATE.format(
        group_id=group_id,
        volume_root_lines=quoted_lines(volume_roots),
        src_lines=quoted_lines([src for src, _ in jobs]),
        dest_lines=quoted_lines([dest_dir for _, dest_dir in jobs]),
    )


SCRIPT_TEMPLATE = """#!/bin/bash
# Auto-generated by FITS_Report (siril_export) for target group {group_id}.
# Copies this group's Light frames from their source location into the
# flat lights/ folder(s) alongside this script, ready for Siril.
#
# Safe to re-run: existing files are never deleted, and you're asked
# before anything already present gets overwritten.

set -uo pipefail

VOLUME_ROOTS=(
{volume_root_lines}
)

SRCS=(
{src_lines}
)

DESTS=(
{dest_lines}
)

total=${{#SRCS[@]}}
copied=0
skipped_exists=0
skipped_missing=0
failed=0
overwrite_all=0
skip_all=0

summary() {{
    echo ""
    echo "---- Summary ----"
    echo "Copied:                    $copied"
    echo "Skipped (already existed): $skipped_exists"
    echo "Skipped (source missing):  $skipped_missing"
    echo "Failed:                    $failed"
    echo "Total queued:              $total"
}}

trap 'echo ""; echo "Interrupted."; summary; exit 130' INT TERM

echo "Checking that source volume(s) are mounted..."
for root in "${{VOLUME_ROOTS[@]}}"; do
    if ! mount | grep -qF " on ${{root}} "; then
        echo "ERROR: '$root' does not appear to be mounted. Mount it and re-run this script." >&2
        exit 1
    fi
    echo "  OK: $root"
done

for ((i = 0; i < total; i++)); do
    src="${{SRCS[$i]}}"
    dest_dir="${{DESTS[$i]}}"
    name="$(basename "$src")"
    dest="$dest_dir/$name"
    n=$((i + 1))

    printf '[%d/%d] %s\\n' "$n" "$total" "$name"

    if [ ! -e "$src" ]; then
        echo "  SKIP (source not found): $src" >&2
        skipped_missing=$((skipped_missing + 1))
        continue
    fi

    action="overwrite"
    if [ -e "$dest" ]; then
        if [ "$skip_all" -eq 1 ]; then
            action="skip"
        elif [ "$overwrite_all" -eq 1 ]; then
            action="overwrite"
        else
            read -r -p "  '$dest' already exists. Overwrite? [y]es/[N]o/[a]ll/[s]kip-all: " ans
            case "$ans" in
                [Aa]*) overwrite_all=1; action="overwrite" ;;
                [Ss]*) skip_all=1; action="skip" ;;
                [Yy]*) action="overwrite" ;;
                *) action="skip" ;;
            esac
        fi
    fi

    if [ "$action" = "skip" ]; then
        echo "  skip: $dest"
        skipped_exists=$((skipped_exists + 1))
        continue
    fi

    mkdir -p "$dest_dir"
    if cp -p "$src" "$dest"; then
        copied=$((copied + 1))
    else
        echo "  FAILED to copy: $src" >&2
        failed=$((failed + 1))
    fi
done

summary
"""
