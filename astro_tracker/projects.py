"""Projects and Checkouts: defining what will be processed and recording exactly what was handed out.

Sits between the API and the storage/manifest modules. A Project is a
Target being processed; a Checkout is one hand-out of subs for it, fixed
at the moment it is created. Changing the selection makes a new
Checkout -- an existing one is never edited, because outputs checked in
against it rely on its manifest saying what was actually there.
"""

import json
import os

from astro_tracker import config, library_storage, manifest, storage, vocabulary


class ProjectError(Exception):
    pass


def project_dir(project, root=None):
    """Where a Project's files live under the projects root: <root>/<target>/<project slug>. None if no root is set."""
    root = root or config.projects_root()
    if not root:
        return None
    return os.path.join(root, vocabulary.slug(project["target_name"]), project["slug"])


def create_project(conn, target_group_id, name=None, notes=None):
    """Create a Project for a target group. The name defaults to the Target's name."""
    target_name = library_storage.get_target_name(conn, target_group_id)
    if target_name is None:
        raise ProjectError(f"Target group {target_group_id} does not exist or has no Target name yet")
    name = (name or "").strip() or target_name
    slug = vocabulary.unique_name(vocabulary.slug(name), library_storage.get_project_slugs(conn))
    return library_storage.create_project(conn, slug, name, target_group_id, target_name, notes)


def checkout_options(conn, project):
    """The sessions, Rigs and Filters available for a Project's Target, with counts."""
    lights = library_storage.get_lights_for_target_group(conn, project["target_group_id"])
    return manifest.summarize_options(lights)


def _selection_sets(selection):
    def as_set(key):
        values = selection.get(key)
        return set(values) if values is not None else None
    return as_set("session_ids"), as_set("rigs"), as_set("filters")


def preview_checkout(conn, project, selection):
    """Build, without storing, the manifest a selection would produce."""
    lights = library_storage.get_lights_for_target_group(conn, project["target_group_id"])
    session_ids, rigs, filters = _selection_sets(selection)
    chosen = manifest.select_lights(lights, session_ids, rigs, filters)
    return manifest.build_manifest(chosen, storage.get_duplicate_exclusion_ids(conn))


def create_checkout(conn, project, selection, root=None):
    """Create the Project's next Checkout from a selection and write its manifest.json.

    Raises ProjectError when the selection yields no subs -- an empty
    Checkout would record a hand-out that never happened.
    """
    built = preview_checkout(conn, project, selection)
    if built["sub_count"] == 0:
        raise ProjectError("The selection contains no subs that can be checked out")
    checkout_id = library_storage.create_checkout(conn, project["id"], selection, built)
    write_manifest_file(conn, checkout_id, root)
    return checkout_id


def write_manifest_file(conn, checkout_id, root=None):
    """Write checkouts/<NN>/manifest.json in the Project folder. Returns its path, or None with no projects root."""
    stored = library_storage.get_checkout_manifest(conn, checkout_id)
    project = library_storage.get_project(conn, stored["project"]["id"])
    base = project_dir(project, root)
    if base is None:
        return None
    folder = os.path.join(base, "checkouts", f"{stored['checkout']['number']:02d}")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "manifest.json")
    with open(path + ".part", "w") as f:
        json.dump(stored, f, indent=2)
    os.replace(path + ".part", path)
    return path
