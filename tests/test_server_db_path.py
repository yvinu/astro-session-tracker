import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = """
import runpy, sys, uvicorn
uvicorn.run = lambda *args, **kwargs: None
sys.argv = ["server", "--db", sys.argv[1]]
runpy.run_module("astro_tracker.server", run_name="__main__")
from astro_tracker import library_api
print(library_api._db_path())
"""


def test_db_flag_reaches_library_routes_when_server_is_run_as_a_script(tmp_path):
    """`python -m astro_tracker.server --db X` must make every route use X.

    Regression test: the library routes once looked the path up on a
    second copy of the server module and used the default catalog.
    """
    db = str(tmp_path / "chosen.db")
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, db], capture_output=True, text=True, cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": REPO, "ASTRO_TRACKER_DB": ""},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == db
    assert not os.path.exists(os.path.join(str(tmp_path), "astro_inventory.db"))
