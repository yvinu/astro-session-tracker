"""Auto-derive imaging sessions from each file's target group + observation night.

Pure logic, no I/O. Runs conceptually after FOV clustering (clustering.py)
so sessions reflect true sky-position targets, not raw OBJECT label
matches -- a "session" is one night's worth of subs on one target group.
"""

from datetime import datetime, timedelta

# Night boundary: local noon, approximated via UTC noon since we don't have
# per-file timezone/location info. This means an observation that runs past
# local midnight still counts as the same "night" it started on, which is
# the standard astronomical convention.
NIGHT_BOUNDARY_HOUR = 12


def derive_observation_night(date_obs):
    """Bucket a DATE-OBS header value into a YYYY-MM-DD observation-night string.

    Returns "Unknown" for a missing or unparseable value rather than
    raising, so files with bad/missing dates still land in a session
    (an "Unknown"-night one) instead of being silently dropped.
    """
    if not date_obs or date_obs == "Unknown":
        return "Unknown"

    text = str(date_obs).strip()
    if text.endswith("Z"):
        text = text[:-1]

    # A bare "YYYY-MM-DD" (no time component) has nothing to apply the noon
    # boundary to -- fromisoformat happily parses it as midnight, which
    # would otherwise shift it back onto the previous night.
    has_time_component = len(text) > 10

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
            has_time_component = False
        except ValueError:
            return "Unknown"

    if has_time_component:
        dt = dt - timedelta(hours=NIGHT_BOUNDARY_HOUR)
    return dt.date().isoformat()


def derive_sessions(files):
    """Group files into sessions keyed by (target_group_id, observation_night).

    `files` is an iterable of dicts with 'id', 'target_group_id', and
    'date' keys. Files with no target_group_id (ungrouped -- missing or
    malformed RA/DEC) are excluded: a session represents a night on a
    sky-position-recognized target, which an ungrouped file isn't.

    Returns dict[(target_group_id, observation_night) -> list of file ids].
    """
    sessions = {}
    for f in files:
        target_group_id = f.get("target_group_id")
        if target_group_id is None:
            continue
        night = derive_observation_night(f.get("date"))
        key = (target_group_id, night)
        sessions.setdefault(key, []).append(f["id"])
    return sessions
