"""The Rig registry: registering, changing and removing Rigs.

A Rig edit changes which Files it claims, so every change here ends by
reassigning Rigs across the library. The rules for what makes a valid
Rig live here, not in the route that receives the form.
"""

from astro_tracker import library_storage, vocabulary, vocabulary_job


class RigError(ValueError):
    """A Rig that cannot be saved as given. The message is for the user."""


def listing(conn):
    """Registered Rigs, every Optical Train in the library, and Rigs suggested for the unassigned ones."""
    trains = library_storage.get_optical_train_summary(conn)
    return {"rigs": library_storage.get_rigs(conn), "optical_trains": trains,
            "suggestions": vocabulary.suggest_rigs(trains)}


def save(conn, rig_id, name, patterns=(), date_ranges=(), camera=None, focal_min=None, focal_max=None,
         focal_nominal=None):
    """Create or update a Rig and reassign every File. Returns {"rig", "recompute"}. Raises RigError.

    A Rig matches by camera (with an optional measured focal-length
    range), by Optical Train patterns, or both; it needs at least one.
    The nominal focal length is what the pages show for the Rig's Files
    and plays no part in matching.
    """
    if not rig_id or vocabulary.slug(rig_id, "") != rig_id:
        raise RigError("Rig id may contain only letters, digits, dot and hyphen")
    patterns = [p.strip() for p in patterns if p and p.strip()]
    camera = vocabulary.normalize_camera(camera)
    if not patterns and not camera:
        raise RigError("A Rig needs a camera or at least one Optical Train pattern")
    if (focal_min is not None or focal_max is not None) and not camera:
        raise RigError("A focal length range needs a camera to go with it")
    if any(value is not None and value <= 0 for value in (focal_min, focal_max, focal_nominal)):
        raise RigError("Focal lengths must be greater than zero")
    if focal_min is not None and focal_max is not None and focal_min > focal_max:
        raise RigError("The focal length range is the wrong way round")
    date_ranges = [list(r) for r in date_ranges]
    if any(len(r) != 2 for r in date_ranges):
        raise RigError("Each date range is [start, end]; either may be null")
    if any(start and end and start > end for start, end in date_ranges):
        raise RigError("A date range ends before it starts")

    rig = library_storage.upsert_rig(conn, rig_id, (name or "").strip() or rig_id, patterns, date_ranges,
                                     camera, focal_min, focal_max, focal_nominal)
    return {"rig": rig, "recompute": vocabulary_job.recompute(conn)}


def remove(conn, rig_id):
    """Remove a Rig and reassign every File. Returns the reassignment summary, or None if there was no such Rig."""
    if not library_storage.delete_rig(conn, rig_id):
        return None
    return vocabulary_job.recompute(conn)
