"""Check-in: store what came back from processing, named consistently and linked to what went in.

Each check-in is a run -- one pass through one tool. Its logs, settings
and project files are kept under the run's own folder with the names
the tool gave them. Stacks and finals are different: they are what
someone later looks for by name, so they are stored under a Canonical
Name (vocabulary.canonical_name) in stacks/ or finals/, and the name the
tool gave them is kept in the catalog.

    projects/<target>/<project>/
      runs/<NN>_<stacker>/   stacking run: logs, conversion files, settings
      post/<NN>_<tool>/      post-processing run: logs, project files
      stacks/                linear images, canonical names
      finals/                finished images, canonical names
      record.json, record.md

A file is written to a temporary place inside the Project folder, its
hash checked against what the sender declared, and only then moved into
place and recorded -- so an interrupted upload leaves no Artifact.
"""

import hashlib
import json
import os
import uuid

from astro_tracker import checkin_kinds, library_storage, projects, vocabulary

RUN_KINDS = ("stacking", "post")
INCOMING_DIR = ".incoming"

STATUS_STORED = "stored"
STATUS_EXISTS = "exists"


class CheckinError(Exception):
    pass


def run_folder(run):
    """A run's folder relative to the Project folder: runs/NN_tool for stacking, post/NN_tool otherwise."""
    parent = "runs" if run["kind"] == "stacking" else "post"
    return f"{parent}/{run['number']:02d}_{vocabulary.slug(run['tool'])}"


def start_run(conn, project, kind, tool, checkout_id=None, notes=None):
    """Open a run for a Project. It works from the given Checkout, or the Project's latest.

    A run with no Checkout is allowed (e.g. Photoshop work on a final
    from an earlier run), but it then has no subs behind it.
    """
    if kind not in RUN_KINDS:
        raise CheckinError(f"Run kind must be one of {', '.join(RUN_KINDS)}")
    if checkout_id is None:
        checkout_id = library_storage.get_latest_checkout_id(conn, project["id"])
    return library_storage.create_run(conn, project["id"], checkout_id, kind, (tool or "unknown").strip(), notes)


def incoming_path(project, root=None):
    """A fresh temporary path inside the Project folder for an upload in progress."""
    base = projects.project_dir(project, root)
    if base is None:
        raise CheckinError("No projects root is configured (ASTRO_PROJECTS_ROOT), so there is nowhere to store files")
    folder = os.path.join(base, INCOMING_DIR)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, uuid.uuid4().hex + ".part")


def _hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_relpath(relpath, taken):
    if relpath not in taken:
        return relpath
    stem, ext = os.path.splitext(relpath)
    n = 2
    while f"{stem}-{n}{ext}" in taken:
        n += 1
    return f"{stem}-{n}{ext}"


def _name_fields(conn, run, original_name, rig, filter_name, frames):
    """Rig, Filter, frame count and exposure for an image's Canonical Name.

    Anything the sender did not state is taken from the run's Checkout:
    the single Rig/Filter if there is one, else "multi"; the frame count
    a tool wrote into the file name, else the number of subs handed out.
    """
    groups = library_storage.get_checkout_groups(conn, run["checkout_id"]) if run["checkout_id"] else []
    rig = rig or vocabulary.one_or_multi(g["rig"] for g in groups)
    filter_name = filter_name or vocabulary.one_or_multi(g["filter"] for g in groups)
    matching = [g for g in groups if rig in (g["rig"], vocabulary.MULTI) and filter_name in (g["filter"], vocabulary.MULTI)]
    if frames is None:
        frames = checkin_kinds.guess_frames(original_name)
    if frames is None:
        frames = sum(g["count"] for g in matching)
    exposures = {g["exposure"] for g in matching if g["exposure"]}
    exposure = exposures.pop() if len(exposures) == 1 else 0
    return rig, filter_name, frames, exposure


def store_artifact(conn, project, run, temp_path, original_relpath, kind,
                   declared_hash=None, stage=None, rig=None, filter_name=None, frames=None, root=None):
    """Move an uploaded file into the Project folder and record it. Returns (artifact, status).

    Status is "exists" when the Project already holds a file with the
    same Content hash -- nothing is stored twice, which is what makes a
    repeated check-in upload nothing. An image whose content changed gets
    the next version number; earlier versions are kept.

    Raises CheckinError, having removed the temporary file, if the bytes
    received do not match `declared_hash`.
    """
    base = projects.project_dir(project, root)
    try:
        content_hash = _hash(temp_path)
        if declared_hash and declared_hash != content_hash:
            raise CheckinError(f"{original_relpath}: received bytes do not match the hash sent with them")
        existing = library_storage.find_artifact_by_hash(conn, project["id"], content_hash)
        if existing is not None:
            os.remove(temp_path)
            return existing, STATUS_EXISTS

        original_name = original_relpath.split("/")[-1]
        fields = {
            "project_id": project["id"], "run_id": run["id"], "kind": kind,
            "original_name": original_name, "original_relpath": original_relpath,
            "content_hash": content_hash, "size": os.path.getsize(temp_path),
        }
        taken = library_storage.get_stored_relpaths(conn, project["id"])

        if kind == checkin_kinds.KIND_IMAGE:
            if stage not in vocabulary.STAGES:
                raise CheckinError(f"{original_relpath}: an image needs a Stage, one of {', '.join(vocabulary.STAGES)}")
            rig, filter_name, frames, exposure = _name_fields(conn, run, original_name, rig, filter_name, frames)
            version = library_storage.get_next_artifact_version(conn, project["id"], rig, filter_name, stage)
            name = vocabulary.canonical_name(
                project["target_name"], rig, filter_name, stage, frames, exposure, version,
                os.path.splitext(original_name)[1],
            )
            folder = "finals" if stage == "final" else "stacks"
            fields.update(stage=stage, rig=rig, filter=filter_name, frames=frames, exposure=exposure, version=version,
                          stored_relpath=_unique_relpath(f"{folder}/{name}", taken))
        else:
            fields["stored_relpath"] = _unique_relpath(f"{run_folder(run)}/{original_name}", taken)

        destination = os.path.join(base, fields["stored_relpath"])
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        os.replace(temp_path, destination)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return library_storage.insert_artifact(conn, fields), STATUS_STORED


def finish_run(conn, project, run, root=None):
    """Close a run: drop it if it ended up empty, then rewrite the Project's record files.

    A run with no files and no notes records nothing that happened, and
    would otherwise be left behind by a check-in that found nothing new.
    """
    runs = {r["id"]: r for r in library_storage.get_runs(conn, project["id"])}
    current = runs.get(run["id"])
    if current is not None and not current["artifacts"] and not (current["notes"] or "").strip():
        library_storage.delete_run(conn, run["id"])
        current = None
    write_record(conn, project, root)
    return current


def build_record(conn, project):
    """Everything known about a Project, as one document: Checkouts, runs, outputs and the subs behind them."""
    runs = library_storage.get_runs(conn, project["id"])
    checkouts = {c["id"]: c for c in library_storage.get_checkouts(conn, project["id"])}
    return {
        "project": project,
        "checkouts": list(checkouts.values()),
        "runs": [
            {
                "number": run["number"], "kind": run["kind"], "tool": run["tool"], "notes": run["notes"],
                "created_at": run["created_at"], "folder": run_folder(run),
                "checkout_number": checkouts[run["checkout_id"]]["number"] if run["checkout_id"] in checkouts else None,
                "outputs": [
                    {k: a[k] for k in ("stage", "stored_relpath", "original_name", "version", "rig", "filter",
                                       "frames", "exposure", "content_hash", "size")}
                    for a in run["artifacts"] if a["stage"]
                ],
                "files": [{k: a[k] for k in ("kind", "stored_relpath", "original_relpath", "content_hash", "size")}
                          for a in run["artifacts"] if not a["stage"]],
            }
            for run in runs
        ],
    }


def render_record_markdown(record):
    project = record["project"]
    lines = [f"# {project['name']}", "", f"Target: {project['target_name']}  ", f"Status: {project['status']}", ""]
    if project.get("notes"):
        lines += [project["notes"], ""]

    lines += ["## Checkouts", ""]
    for c in record["checkouts"]:
        hours = (c["integration_seconds"] or 0) / 3600
        lines.append(f"- Checkout {c['number']:02d} ({c['created_at'][:10]}): {c['sub_count']} subs, {hours:.2f} h")
    if not record["checkouts"]:
        lines.append("None yet.")

    lines += ["", "## Runs", ""]
    for run in record["runs"]:
        source = f"checkout {run['checkout_number']:02d}" if run["checkout_number"] else "no checkout"
        lines += [f"### {run['number']:02d} {run['tool']} ({run['kind']}, {run['created_at'][:10]}, from {source})", ""]
        if run["notes"]:
            lines += [run["notes"], ""]
        for output in run["outputs"]:
            lines.append(f"- **{output['stage']}** `{output['stored_relpath']}` (was `{output['original_name']}`)")
        for item in run["files"]:
            lines.append(f"- {item['kind']}: `{item['stored_relpath']}`")
        lines.append("")
    if not record["runs"]:
        lines.append("None yet.")
    return "\n".join(lines).rstrip() + "\n"


def write_record(conn, project, root=None):
    """Rewrite record.json and record.md in the Project folder from the catalog. No-op without a projects root."""
    base = projects.project_dir(project, root)
    if base is None:
        return None
    os.makedirs(base, exist_ok=True)
    record = build_record(conn, library_storage.get_project(conn, project["id"]))
    for name, text in (("record.json", json.dumps(record, indent=2)), ("record.md", render_record_markdown(record))):
        path = os.path.join(base, name)
        with open(path + ".part", "w") as f:
            f.write(text)
        os.replace(path + ".part", path)
    return base
