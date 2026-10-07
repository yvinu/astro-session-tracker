"""Build a Checkout manifest: the exact list of subs handed out for a Project.

Pure logic, no I/O. The manifest is what provenance rests on -- every
output checked in later is linked to the Checkout it came from, and
through the manifest to these subs -- so it records each sub's Content
hash, and it is never changed once created.

Subs are grouped by Rig and Filter, because frames from different
optical configurations or filters are never stacked as one set. Within a
group each sub has a position: its place in case-insensitive file-name
order. That is the order Siril's `link` numbers the files of a folder
in (lights_00001, lights_00002, ...), observed in a real conversion
file, and Siril's logs name frames only by that number. Recording the
position is what lets a log line about frame 37 be traced to a file
when Siril's own conversion file was not kept.
"""

UNASSIGNED_RIG = "unassigned"


def group_key(rig, filter_name):
    return f"{rig}__{filter_name}"


def select_lights(files, session_ids=None, rigs=None, filters=None):
    """Narrow a target's light subs to the chosen sessions, Rigs and Filters. None means no restriction."""
    chosen = []
    for f in files:
        if session_ids is not None and f.get("session_id") not in session_ids:
            continue
        if rigs is not None and (f.get("rig_id") or UNASSIGNED_RIG) not in rigs:
            continue
        if filters is not None and f.get("filter_canonical") not in filters:
            continue
        chosen.append(f)
    return chosen


def build_manifest(files, duplicate_exclusion_ids=()):
    """Turn selected sub records into manifest groups, plus a count of what was left out and why.

    `files` are dicts with id, path, file_name, content_hash, session_id,
    night, rig_id, filter_canonical, exposure and size. Left out:

      duplicates       non-representative copies of a duplicate group
                       (see ADR-0002) -- each exposure is handed out once
      no_hash          no current Content hash, so the copy handed out
                       could not be verified or traced
      name_collisions  a second file with the same name in the same
                       group, which a flat lights/ folder cannot hold

    Returns {"groups": [...], "left_out": {...}, "sub_count": n, "integration_seconds": s}.
    """
    left_out = {"duplicates": 0, "no_hash": 0, "name_collisions": 0}
    by_group = {}
    for f in files:
        if f["id"] in duplicate_exclusion_ids:
            left_out["duplicates"] += 1
            continue
        if not f.get("content_hash"):
            left_out["no_hash"] += 1
            continue
        rig = f.get("rig_id") or UNASSIGNED_RIG
        filter_name = f.get("filter_canonical") or "NONE"
        by_group.setdefault((rig, filter_name), []).append(f)

    groups = []
    for (rig, filter_name), members in sorted(by_group.items()):
        members.sort(key=lambda f: (f["file_name"].lower(), f["file_name"], f["path"]))
        entries, seen_names = [], set()
        for f in members:
            folded = f["file_name"].lower()
            if folded in seen_names:
                left_out["name_collisions"] += 1
                continue
            seen_names.add(folded)
            entries.append({
                "position": len(entries) + 1,
                "file_id": f["id"],
                "path": f["path"],
                "file_name": f["file_name"],
                "content_hash": f["content_hash"],
                "handed_hash": f["content_hash"],
                "session_id": f.get("session_id"),
                "night": f.get("night"),
                "exposure": f.get("exposure") or 0,
                "size": f.get("size") or 0,
            })
        groups.append({
            "key": group_key(rig, filter_name),
            "rig": rig,
            "filter": filter_name,
            "count": len(entries),
            "integration_seconds": sum(e["exposure"] for e in entries),
            "bytes": sum(e["size"] for e in entries),
            "entries": entries,
        })

    return {
        "groups": groups,
        "left_out": left_out,
        "sub_count": sum(g["count"] for g in groups),
        "integration_seconds": sum(g["integration_seconds"] for g in groups),
    }


def summarize_options(files):
    """The sessions, Rigs and Filters present among a target's lights, with counts, for the selection form."""
    def tally(key_fn, label_fn=None):
        counts = {}
        for f in files:
            key = key_fn(f)
            entry = counts.setdefault(key, {"value": key, "count": 0, "integration_seconds": 0})
            entry["count"] += 1
            entry["integration_seconds"] += f.get("exposure") or 0
            if label_fn:
                entry["label"] = label_fn(f)
        return sorted(counts.values(), key=lambda e: str(e.get("label", e["value"])))

    return {
        "sessions": tally(lambda f: f.get("session_id"), lambda f: f.get("night") or "Unknown"),
        "rigs": tally(lambda f: f.get("rig_id") or UNASSIGNED_RIG),
        "filters": tally(lambda f: f.get("filter_canonical")),
    }
