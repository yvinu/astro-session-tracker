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
