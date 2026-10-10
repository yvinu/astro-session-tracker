"""`astro checkout`: copy a Checkout's subs into a working folder and verify every one.

The service decides what is in a Checkout; this command only fetches
it. Each file is checked against the hash in the manifest after
copying, so what sits in the working folder is known to be exactly what
the manifest says. Re-running is safe: files already present and
correct are left alone, so an interrupted checkout just carries on.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile

from astro_tracker import checkout_layout
from astro_tracker.checkin_kinds import MANIFEST_FILE

from astro_cli import settings


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_local(pairs):
    """Copy (source, destination) pairs on this machine, each via a temporary name."""
    for source, destination in pairs:
        part = destination + ".part"
        shutil.copy2(source, part)
        os.replace(part, destination)


def copy_rsync(pairs):
    """Fetch (remote source, destination) pairs with rsync, one invocation per source folder and destination."""
    batches = {}
    for source, destination in pairs:
        folder, name = source.rsplit("/", 1)
        batches.setdefault((folder, os.path.dirname(destination)), []).append(name)
    for (folder, dest_dir), names in batches.items():
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as listing:
            listing.write("\n".join(names) + "\n")
        try:
            subprocess.run(
                ["rsync", "-a", "--partial", f"--files-from={listing.name}", folder + "/", dest_dir + "/"],
                check=True,
            )
        finally:
            os.remove(listing.name)


def run(api, project_ref, profile, dest, config, out=print, local_copy=copy_local, remote_copy=copy_rsync):
    """Check out the latest Checkout of a Project. Returns a summary dict; `failed` lists files that did not verify."""
    stored = api.get_json(f"/api/cli/projects/{project_ref}/manifest")
    plan = checkout_layout.plan_layout(stored, profile)
    working = dest or os.path.join(config.get("work_root") or os.getcwd(), checkout_layout.working_folder_name(stored))
    os.makedirs(working, exist_ok=True)

    summary = {"working_dir": working, "copied": 0, "already_present": 0, "failed": []}
    for group in plan:
        lights_dir = os.path.join(working, group["lights_dir"])
        os.makedirs(lights_dir, exist_ok=True)

        needed = []
        for entry in group["entries"]:
            destination = os.path.join(lights_dir, entry["file_name"])
            if os.path.exists(destination) and sha256(destination) == entry["handed_hash"]:
                summary["already_present"] += 1
            else:
                needed.append((entry, settings.map_path(entry["path"], config.get("path_map")), destination))
        out(f"{group['rig']} / {group['filter']}: {len(group['entries'])} subs, {len(needed)} to copy -> {lights_dir}")

        local = [(src, dst) for _e, src, dst in needed if not settings.is_remote(src)]
        remote = [(src, dst) for _e, src, dst in needed if settings.is_remote(src)]
        try:
            if local:
                local_copy(local)
            if remote:
                remote_copy(remote)
        except (OSError, subprocess.CalledProcessError) as e:
            out(f"  copy stopped: {e}")

        for entry, _source, destination in needed:
            if os.path.exists(destination) and sha256(destination) == entry["handed_hash"]:
                summary["copied"] += 1
            else:
                # A wrong file must not be left looking like a checked-out sub.
                if os.path.exists(destination):
                    os.remove(destination)
                summary["failed"].append(os.path.join(group["lights_dir"], entry["file_name"]))

    with open(os.path.join(working, MANIFEST_FILE), "w") as f:
        json.dump(stored, f, indent=2)
    if not summary["failed"]:
        api.post_json(f"/api/cli/checkouts/{stored['checkout']['id']}/working-dir", {"working_dir": working})
    return summary
