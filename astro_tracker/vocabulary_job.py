"""Apply the vocabularies to the catalog: assign each File a Rig and canonical Filter, name each Target.

Runs with the other derived data (clustering, sessions, duplicates) and
again whenever a Rig or a filter mapping is edited. Reads and writes the
catalog only; no file on disk is touched.
"""

from astro_tracker import library_storage, vocabulary


def recompute(conn):
    """Recompute Rig and Filter for every file and give unnamed target groups a default name.

    A target group's name, once set, is left alone here: target group ids
    are kept stable across re-clustering (see storage.save_clustering),
    so the name -- like session annotations -- stays attached.

    Returns a summary dict.
    """
    library_storage.tag_source_files(conn)

    rigs = library_storage.get_rigs(conn)
    filter_map = library_storage.get_filter_map(conn)

    updates = []
    status_counts = {vocabulary.RIG_ASSIGNED: 0, vocabulary.RIG_UNASSIGNED: 0, vocabulary.RIG_AMBIGUOUS: 0}
    for f in library_storage.get_files_for_vocabulary(conn):
        rig_id, status = vocabulary.assign_rig(f["optical_train"], f["date"], rigs, f["instrument"], f["focal_length"])
        canonical = vocabulary.canonical_filter(f["filter"], filter_map)
        status_counts[status] += 1
        if (rig_id, status, canonical) != (f["rig_id"], f["rig_status"], f["filter_canonical"]):
            updates.append((rig_id, status, canonical, f["id"]))
    library_storage.save_file_vocabulary(conn, updates)
    conn.commit()

    named = 0
    labels_by_group = library_storage.get_target_labels_by_group(conn)
    targets = library_storage.get_target_names(conn)
    taken = {t["name"] for t in targets if t["name"]}
    for target in targets:
        if target["name"]:
            continue
        default = vocabulary.default_target_name(labels_by_group.get(target["target_group_id"], []))
        name = vocabulary.unique_name(default, taken)
        library_storage.set_target_name(conn, target["target_group_id"], name, is_custom=False)
        taken.add(name)
        named += 1

    return {
        "files_changed": len(updates),
        "rig_assigned": status_counts[vocabulary.RIG_ASSIGNED],
        "rig_unassigned": status_counts[vocabulary.RIG_UNASSIGNED],
        "rig_ambiguous": status_counts[vocabulary.RIG_AMBIGUOUS],
        "targets_named": named,
    }
