import threading

import pytest

from astro_tracker import jobs


def test_job_reports_result_when_done():
    runner = jobs.JobRunner()
    runner.start("k", lambda job: {"n": 3}, wait=True)
    status = runner.status("k")
    assert status["state"] == jobs.STATE_DONE and status["result"] == {"n": 3}


def test_second_start_with_same_key_is_rejected_while_running():
    runner = jobs.JobRunner()
    release = threading.Event()
    runner.start("k", lambda job: release.wait(5))
    with pytest.raises(jobs.JobAlreadyRunningError):
        runner.start("k", lambda job: None)
    runner.start("other", lambda job: None, wait=True)
    release.set()


def test_same_key_can_run_again_after_finishing():
    runner = jobs.JobRunner()
    runner.start("k", lambda job: 1, wait=True)
    runner.start("k", lambda job: 2, wait=True)
    assert runner.status("k")["result"] == 2


def test_cancel_marks_a_cooperative_job_cancelled():
    runner = jobs.JobRunner()
    started = threading.Event()

    def work(job):
        started.set()
        while not job.should_stop():
            pass

    runner.start("k", work)
    started.wait(5)
    assert runner.cancel("k") is True
    for _ in range(1000):
        if runner.status("k")["state"] != jobs.STATE_RUNNING:
            break
        threading.Event().wait(0.005)
    assert runner.status("k")["state"] == jobs.STATE_CANCELLED
    assert runner.cancel("k") is False


def test_exception_marks_job_failed_with_its_message():
    runner = jobs.JobRunner()

    def boom(job):
        raise RuntimeError("no disk")

    runner.start("k", boom, wait=True)
    status = runner.status("k")
    assert status["state"] == jobs.STATE_FAILED and status["error"] == "no disk"


def _wait_until(condition, seconds=10):
    import time
    deadline = time.time() + seconds
    while not condition():
        assert time.time() < deadline, "timed out"
        time.sleep(0.005)


def _held_queue_job(runner, key="first"):
    """Submit a queued job that runs until released. Returns the release event."""
    running, release = threading.Event(), threading.Event()

    def work(job):
        running.set()
        release.wait(5)
        return key

    runner.submit(key, work, lane=jobs.LANE_QUEUE)
    running.wait(5)
    return release


def test_queued_jobs_run_one_at_a_time_in_order():
    runner = jobs.JobRunner()
    order = []
    release = _held_queue_job(runner)
    second = runner.submit("second", lambda job: order.append("second"), lane=jobs.LANE_QUEUE)
    third = runner.submit("third", lambda job: order.append("third"), lane=jobs.LANE_QUEUE)

    assert second["state"] == jobs.STATE_WAITING and third["state"] == jobs.STATE_WAITING
    assert [j["key"] for j in runner.list()["waiting"]] == ["second", "third"]
    assert order == []

    release.set()
    _wait_until(lambda: runner.get(third["id"])["state"] == jobs.STATE_DONE)
    assert order == ["second", "third"]


def test_a_waiting_request_for_the_same_key_is_merged():
    runner = jobs.JobRunner()
    release = _held_queue_job(runner)
    first = runner.submit("ingest:/a", lambda job: None, lane=jobs.LANE_QUEUE)
    again = runner.submit("ingest:/a", lambda job: None, lane=jobs.LANE_QUEUE)

    assert again["id"] == first["id"]
    assert len(runner.list()["waiting"]) == 1
    release.set()


def test_a_request_for_a_key_that_is_running_waits_for_a_fresh_turn():
    runner = jobs.JobRunner()
    release = _held_queue_job(runner, key="ingest:/a")
    again = runner.submit("ingest:/a", lambda job: "second pass", lane=jobs.LANE_QUEUE)

    assert again["state"] == jobs.STATE_WAITING
    release.set()
    _wait_until(lambda: runner.get(again["id"])["state"] == jobs.STATE_DONE)
    assert runner.get(again["id"])["result"] == "second pass"


def test_a_waiting_job_can_be_cancelled_and_never_runs():
    runner = jobs.JobRunner()
    ran = []
    release = _held_queue_job(runner)
    doomed = runner.submit("doomed", lambda job: ran.append("doomed"), lane=jobs.LANE_QUEUE)
    kept = runner.submit("kept", lambda job: ran.append("kept"), lane=jobs.LANE_QUEUE)

    assert runner.cancel_job(doomed["id"]) is True
    assert runner.get(doomed["id"])["state"] == jobs.STATE_CANCELLED
    assert runner.cancel_job(doomed["id"]) is False

    release.set()
    _wait_until(lambda: runner.get(kept["id"])["state"] == jobs.STATE_DONE)
    assert ran == ["kept"]


def test_cancel_waiting_cancels_everything_not_yet_started_and_leaves_the_running_job():
    runner = jobs.JobRunner()
    release = _held_queue_job(runner)
    runner.submit("a", lambda job: None, lane=jobs.LANE_QUEUE)
    runner.submit("b", lambda job: None, lane=jobs.LANE_QUEUE)

    assert runner.cancel_waiting() == 2
    assert runner.list()["waiting"] == []
    assert [j["key"] for j in runner.list()["running"]] == ["first"]
    release.set()


def test_a_free_job_runs_while_the_queue_is_busy():
    runner = jobs.JobRunner()
    release = _held_queue_job(runner)

    runner.submit("copy", lambda job: "copied", lane=jobs.LANE_FREE, wait=True)

    assert runner.status("copy")["state"] == jobs.STATE_DONE
    assert runner.is_running("first")
    release.set()


def test_a_filler_job_gives_way_to_queued_work_and_resumes_afterwards():
    runner = jobs.JobRunner()
    events = []
    filling = threading.Event()
    remaining = [6]

    def fill(job):
        events.append("fill starts")
        filling.set()
        while remaining[0] > 0:
            if job.should_stop():
                events.append("fill yields")
                return "partial"
            if "queued ran" in events:
                remaining[0] -= 1
            threading.Event().wait(0.002)
        return "all hashed"

    filler = runner.submit("hash", fill, lane=jobs.LANE_FILLER)
    filling.wait(5)
    queued = runner.submit("ingest:/a", lambda job: events.append("queued ran"), lane=jobs.LANE_QUEUE)

    _wait_until(lambda: runner.get(filler["id"])["state"] == jobs.STATE_DONE)
    assert runner.get(queued["id"])["state"] == jobs.STATE_DONE
    assert events == ["fill starts", "fill yields", "queued ran", "fill starts"]
    assert runner.get(filler["id"])["result"] == "all hashed"


def test_a_filler_job_waits_for_the_queue_to_empty_before_starting():
    runner = jobs.JobRunner()
    release = _held_queue_job(runner)
    filler = runner.submit("hash", lambda job: "hashed", lane=jobs.LANE_FILLER)

    assert filler["state"] == jobs.STATE_WAITING
    assert runner.submit("hash", lambda job: "other", lane=jobs.LANE_FILLER)["id"] == filler["id"]

    release.set()
    _wait_until(lambda: runner.get(filler["id"])["state"] == jobs.STATE_DONE)
    assert runner.get(filler["id"])["result"] == "hashed"


def test_a_cancelled_filler_job_is_not_resumed():
    runner = jobs.JobRunner()
    started = threading.Event()

    def fill(job):
        started.set()
        while not job.should_stop():
            threading.Event().wait(0.002)

    filler = runner.submit("hash", fill, lane=jobs.LANE_FILLER)
    started.wait(5)
    assert runner.cancel("hash") is True
    _wait_until(lambda: runner.get(filler["id"])["state"] == jobs.STATE_CANCELLED)
    assert runner.list()["waiting"] == []
