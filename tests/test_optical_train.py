import pytest

from astro_tracker import library_storage, metadata, migrations, optical_train, rigs, storage, vocabulary_job

USER_LABELS = [
    ("OnStep | ZWO ASI294MC Pro | 373mm", "ZWO ASI294MC Pro"),
    ("OnStep | ZWO ASI294MC Pro | 369mm", "ZWO ASI294MC Pro"),
    ("OnStep | ZWO ASI294MC Pro | 374mm", "ZWO ASI294MC Pro"),
    ("OnStep | ZWO ASI294MC Pro | 372.534439682155mm", "ZWO ASI294MC Pro"),
    ("OnStep | ZWO ASI294MC Pro | 372.431561787758mm", "ZWO ASI294MC Pro"),
    ("OnStep | ZWO ASI294MC Pro | 372mm", "ZWO ASI294MC Pro"),
    ("Apertura 60ED 370@F\\6.2 | ZWO CCD ASI294MC Pro | 370.0mm", "ZWO CCD ASI294MC Pro"),
]


# ---- values and labels -------------------------------------------------------

def test_focal_length_value_accepts_numbers_and_text_and_rejects_the_rest():
    assert optical_train.focal_length_value(372.534439682155) == 372.534439682155
    assert optical_train.focal_length_value("370.0") == 370.0
    assert optical_train.focal_length_value("250 mm") == 250.0
    for bad in (None, "", "unknown", 0, -5):
        assert optical_train.focal_length_value(bad) is None


def test_label_joins_what_is_present():
    assert optical_train.label("OnStep", "ZWO ASI294MC Pro", 373) == "OnStep | ZWO ASI294MC Pro | 373mm"
    assert optical_train.label(None, "Seestar S50", None) == "Seestar S50"
    assert optical_train.label(None, None, None) == "Unknown"


def test_nominal_label_of_a_file_with_a_rig_is_the_rigs_name_and_nominal_focal_length():
    rig = {"name": "60ED + 294MC", "focal_nominal": 370.0}
    labels = {optical_train.nominal_label(label, "OnStep", camera, 372.5, rig) for label, camera in USER_LABELS}
    assert labels == {"60ED + 294MC | 370mm"}
    assert optical_train.nominal_label("x", None, "c", 372.5, {"name": "S50", "focal_nominal": None}) == "S50"


def test_nominal_label_of_a_file_without_a_rig_rounds_the_measured_focal_length():
    assert optical_train.nominal_label("OnStep | ZWO ASI294MC Pro | 372.534439682155mm",
                                       "OnStep", "ZWO ASI294MC Pro", 372.534439682155) == "OnStep | ZWO ASI294MC Pro | 373mm"
    assert optical_train.nominal_label("Seestar S50", None, "Seestar S50", None) == "Seestar S50"
    assert optical_train.nominal_label("C8 | 2032.4mm", "C8", "Unknown", 2032.4) == "C8 | 2032mm"


def test_scanning_a_file_stores_telescope_and_focal_length_as_values(make_fits):
    path = make_fits("a.fits", {"IMAGETYP": "Light", "TELESCOP": "OnStep", "INSTRUME": "ZWO ASI294MC Pro",
                                "FOCALLEN": 372.534439682155})
    meta = metadata.get_metadata(path)
    assert meta["telescope"] == "OnStep" and meta["focal_length"] == 372.534439682155
    assert meta["optical_train"] == "OnStep | ZWO ASI294MC Pro | 372.534439682155mm"

    bare = metadata.get_metadata(make_fits("b.fits", {"IMAGETYP": "Light", "INSTRUME": "Seestar S50"}))
    assert bare["telescope"] is None and bare["focal_length"] is None


# ---- migration 8 -------------------------------------------------------------

def test_label_is_taken_apart_using_the_stored_camera():
    split = migrations.split_optical_train_label
    assert split("OnStep | ZWO ASI294MC Pro | 372.534439682155mm", "ZWO ASI294MC Pro") == ("OnStep", 372.534439682155)
    assert split("Apertura 60ED 370@F\\6.2 | ZWO CCD ASI294MC Pro | 370.0mm", "ZWO CCD ASI294MC Pro") == ("Apertura 60ED 370@F\\6.2", 370.0)
    assert split("Seestar S50 | Seestar S50", "Seestar S50") == ("Seestar S50", None)
    assert split("Seestar S50", "Seestar S50") == (None, None)
    assert split("ZWO ASI294MC Pro | 372mm", "ZWO ASI294MC Pro") == (None, 372.0)
    assert split("C8 | 2032mm", "Unknown") == (None, 2032.0)
    assert split("C8 | Some Camera | 2032mm", None) == ("C8", 2032.0)
    assert split("Unknown", "Unknown") == (None, None)
    assert split(None, None) == (None, None)


@pytest.fixture
def catalog_at_version_7(tmp_path):
    """A catalog as the previous release left it: labels only, and one Rig with a focal range."""
    conn = storage.connect(str(tmp_path / "old.db"))
    for migration in migrations.MIGRATIONS[:7]:
        migration(conn)
    conn.execute("PRAGMA user_version = 7")
    rows = USER_LABELS + [("Seestar S50", "Seestar S50"), ("Unknown", "Unknown")]
    for n, (label, camera) in enumerate(rows):
        conn.execute(
            """INSERT INTO files (path, mtime, size, file_name, optical_train, instrument, date, first_seen_at, last_updated_at)
               VALUES (?, 1, 1, ?, ?, ?, '2026-01-01T00:00:00', 't', 't')""",
            (f"/elements/{n}.fit", f"{n}.fit", label, camera))
    conn.execute(
        """INSERT INTO rigs (id, name, patterns, date_ranges, camera, focal_min, focal_max, created_at, updated_at)
           VALUES ('60ed-294', 'My 60ED', '[]', '[]', 'asi294mcpro', 365.3, 377.7, 't', 't')""")
    conn.commit()
    return conn


def test_upgrade_fills_values_from_labels_without_a_rescan(catalog_at_version_7):
    conn = catalog_at_version_7

    storage.init_schema(conn)

    rows = {r["optical_train"]: (r["telescope"], r["focal_length"])
            for r in conn.execute("SELECT optical_train, telescope, focal_length FROM files")}
    assert rows["OnStep | ZWO ASI294MC Pro | 372.534439682155mm"] == ("OnStep", 372.534439682155)
    assert rows["Apertura 60ED 370@F\\6.2 | ZWO CCD ASI294MC Pro | 370.0mm"] == ("Apertura 60ED 370@F\\6.2", 370.0)
    assert rows["Seestar S50"] == (None, None) and rows["Unknown"] == (None, None)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(migrations.MIGRATIONS)


def test_upgrade_keeps_every_file_on_its_rig_and_gives_the_rig_a_nominal_focal_length(catalog_at_version_7):
    conn = catalog_at_version_7

    storage.init_schema(conn)
    summary = vocabulary_job.recompute(conn)

    assert summary["rig_assigned"] == 7 and summary["rig_unassigned"] == 2
    assert library_storage.get_rig(conn, "60ed-294")["focal_nominal"] == 372.0
    shown = {f["optical_train_nominal"] for f in storage.get_all_files(conn) if f["rig_id"]}
    assert shown == {"My 60ED | 372mm"}


# ---- the Rig registry --------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    conn = storage.connect(str(tmp_path / "c.db"))
    storage.init_schema(conn)
    for n, (label, camera) in enumerate(USER_LABELS):
        telescope, focal = migrations.split_optical_train_label(label, camera)
        storage.upsert_file(conn, f"/library/{n}.fit", 1.0, 1, {
            "file_name": f"{n}.fit", "frame_type": "Light", "instrument": camera, "optical_train": label,
            "telescope": telescope, "focal_length": focal, "date": "2026-01-01T00:00:00"})
    conn.commit()
    return conn


def test_saving_a_suggested_rig_claims_every_spelling_and_shows_them_as_one(conn):
    suggestion = rigs.listing(conn)["suggestions"][0]
    assert suggestion["file_count"] == 7

    saved = rigs.save(conn, "60ed-294", "60ED + 294MC", camera=suggestion["camera"],
                      focal_min=suggestion["focal_min"], focal_max=suggestion["focal_max"], focal_nominal=370)

    assert saved["rig"]["focal_nominal"] == 370 and saved["recompute"]["rig_assigned"] == 7
    assert rigs.listing(conn)["suggestions"] == []
    files = storage.get_all_files(conn)
    assert {f["optical_train_nominal"] for f in files} == {"60ED + 294MC | 370mm"}
    assert len({f["optical_train"] for f in files}) == 7


def test_the_nominal_focal_length_plays_no_part_in_matching(conn):
    rigs.save(conn, "r", "R", camera="ASI294MC Pro", focal_min=365, focal_max=378, focal_nominal=2000)
    assert conn.execute("SELECT COUNT(*) FROM files WHERE rig_id = 'r'").fetchone()[0] == 7


def test_removing_a_rig_unassigns_its_files(conn):
    rigs.save(conn, "r", "R", camera="ASI294MC Pro")
    assert rigs.remove(conn, "r")["rig_unassigned"] == 7
    assert rigs.remove(conn, "r") is None
    assert {f["optical_train_nominal"] for f in storage.get_all_files(conn)} >= {"OnStep | ZWO ASI294MC Pro | 373mm"}


@pytest.mark.parametrize("fields, message", [
    ({"rig_id": "has space"}, "Rig id"),
    ({"rig_id": "under_score"}, "Rig id"),
    ({"camera": None, "patterns": ["  "]}, "needs a camera or at least one"),
    ({"camera": "Unknown"}, "needs a camera or at least one"),
    ({"camera": None, "patterns": ["*s50*"], "focal_min": 300}, "needs a camera"),
    ({"focal_min": 380, "focal_max": 360}, "wrong way round"),
    ({"focal_nominal": 0}, "greater than zero"),
    ({"focal_min": -1}, "greater than zero"),
    ({"date_ranges": [["2026-01-01"]]}, "date range"),
    ({"date_ranges": [["2026-03-01", "2026-01-01"]]}, "ends before it starts"),
])
def test_an_invalid_rig_is_refused_with_a_reason_and_nothing_is_saved(conn, fields, message):
    given = {"rig_id": "r", "name": "R", "camera": "ASI294MC Pro", **fields}
    with pytest.raises(rigs.RigError, match=message):
        rigs.save(conn, given.pop("rig_id"), given.pop("name"), **given)
    assert library_storage.get_rigs(conn) == []
