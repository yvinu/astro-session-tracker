"""`astro checkin`: find what a working folder produced and send what is new to the Project.

Looks for outputs and the records of how they were made, leaving out
the checked-out subs and the tools' intermediate files. Everything is
hashed first and the service is asked which hashes it already holds, so
running this again uploads only what has been added or changed since.
"""

import json
import os

from astro_tracker import checkin_kinds as kinds
from astro_tracker.checkout_layout import LIGHTS_DIR

from astro_cli.checkout import sha256


def load_manifest(folder):
    try:
        with open(os.path.join(folder, kinds.MANIFEST_FILE)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def scan(folder, stored_manifest=None, include_attachments=False):
    """List the files in a working folder that check-in would consider, as dicts with relpath and kind.

    A file in a lights/ folder whose name is in the manifest is a
    checked-out sub and is skipped; other files there are kept, because
    some tools save their stack beside the lights.
    """
    sub_names = set()
    if stored_manifest:
        sub_names = {e["file_name"] for g in stored_manifest["groups"] for e in g["entries"]}

    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            relpath = os.path.relpath(os.path.join(root, name), folder).replace(os.sep, "/")
            if os.path.basename(root) == LIGHTS_DIR and name in sub_names:
                continue
            kind = kinds.classify(relpath)
            if kind is None or (kind == kinds.KIND_ATTACHMENT and not include_attachments):
                continue
            found.append({"relpath": relpath, "kind": kind})
    return found


def run(api, project_ref, folder, tool=None, run_kind=None, notes=None, stages=None,
        include_attachments=False, choose_stage=None, out=print):
    """Check a working folder in. Returns a summary dict.

    `stages` maps a relpath to a Stage, overriding the guess; a value of
    "skip" leaves that image out. `choose_stage(relpath, guess)` is asked
    for each remaining image and may return a Stage, "skip", or None to
    accept the guess.
    """
    stages = stages or {}
    stored = load_manifest(folder)
    found = scan(folder, stored, include_attachments)
    for item in found:
        item["path"] = os.path.join(folder, item["relpath"])
        item["sha256"] = sha256(item["path"])

    known = set(api.post_json(f"/api/cli/projects/{project_ref}/known-hashes",
                              {"hashes": [item["sha256"] for item in found]})["known"])
    new = [item for item in found if item["sha256"] not in known]
    summary = {"found": len(found), "already_stored": len(found) - len(new), "stored": [], "skipped": [], "run": None}
    if not new and not notes:
        out("Nothing new to check in.")
        return summary

    # Guessed from everything in the folder, not only what is new: a restack
    # checked in after its log was already stored is still a Siril run.
    suggested_tool, suggested_kind = kinds.suggest_run([(i["relpath"].split("/")[-1], i["kind"]) for i in found])
    # A tool named by the user decides the kind of run; the folder's
    # contents only decide it when no tool was named.
    run_kind = run_kind or (kinds.run_kind_for_tool(tool) if tool else suggested_kind)
    tool = tool or suggested_tool

    for item in new:
        if item["kind"] != kinds.KIND_IMAGE:
            continue
        guess = kinds.guess_stage(item["relpath"], run_kind)
        stage = stages.get(item["relpath"]) or stages.get(item["relpath"].split("/")[-1])
        if stage is None and choose_stage is not None:
            stage = choose_stage(item["relpath"], guess)
        item["stage"] = stage or guess

    body = {"kind": run_kind, "tool": tool, "notes": notes}
    if stored:
        body["checkout_id"] = stored["checkout"]["id"]
    run_info = api.post_json(f"/api/cli/projects/{project_ref}/runs", body)
    out(f"Run {run_info['number']:02d} ({tool}, {run_kind}) -> {run_info['folder']}")

    for item in new:
        if item.get("stage") == "skip":
            summary["skipped"].append(item["relpath"])
            continue
        result = api.put_file(
            f"/api/cli/runs/{run_info['id']}/files",
            {"relpath": item["relpath"], "kind": item["kind"], "sha256": item["sha256"], "stage": item.get("stage")},
            item["path"],
        )
        stored_as = result["artifact"]["stored_relpath"]
        summary["stored"].append({"relpath": item["relpath"], "stored_relpath": stored_as})
        out(f"  {item['relpath']} -> {stored_as}")

    finished = api.post_json(f"/api/cli/runs/{run_info['id']}/finish", {})
    summary["run"] = finished["run"]
    return summary
