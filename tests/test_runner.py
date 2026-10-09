import time

from src.code_agent import runner


def wait_for_done(results):
    deadline = time.monotonic() + 1
    while not results and time.monotonic() < deadline:
        time.sleep(0.01)
    assert results


def test_runner_delivers_success_result(monkeypatch):
    expected = {"files": ["README.md"], "finished": True}
    monkeypatch.setattr(runner.agent, "run_agent", lambda *args, **kwargs: expected)
    results = []

    thread, _ = runner.start_run("key", "doc", "view", "out", lambda _: None, results.append)
    thread.join(timeout=1)

    assert results == [expected]


def test_runner_delivers_readable_error(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("DeepSeek is unavailable")

    monkeypatch.setattr(runner.agent, "run_agent", fail)
    results = []

    thread, _ = runner.start_run("key", "doc", "view", "out", lambda _: None, results.append)
    thread.join(timeout=1)

    assert results == [{"error": "DeepSeek is unavailable"}]


def test_runner_delivers_logs_in_order(monkeypatch):
    def fake_run(*args, log, **kwargs):
        log("planning")
        log("writing files")
        return {"files": []}

    monkeypatch.setattr(runner.agent, "run_agent", fake_run)
    logs = []
    results = []

    thread, _ = runner.start_run("key", "doc", "view", "out", logs.append, results.append)
    thread.join(timeout=1)

    assert logs == ["planning", "writing files"]
    assert results == [{"files": []}]


def test_runner_cancel_event_stops_long_running_agent(monkeypatch):
    def fake_run(*args, cancel_event, **kwargs):
        while not cancel_event.is_set():
            time.sleep(0.01)
        return {"cancelled": True}

    monkeypatch.setattr(runner.agent, "run_agent", fake_run)
    results = []

    thread, cancel_event = runner.start_run("key", "doc", "view", "out", lambda _: None, results.append)
    cancel_event.set()
    thread.join(timeout=1)
    wait_for_done(results)

    assert results == [{"cancelled": True}]


def test_verification_runner_delivers_result_without_api_key(monkeypatch, tmp_path):
    expected = {
        "verification": True,
        "finished": True,
        "tests_passed": True,
        "files": ["README.md"],
    }
    monkeypatch.setattr(
        runner.agent, "verify_project", lambda *args, **kwargs: expected
    )
    results = []
    logs = []

    thread = runner.start_verification(
        "doc.md", "view.md", str(tmp_path), logs.append, results.append
    )
    thread.join(timeout=1)

    assert results == [expected]
    assert logs == []


def test_verification_runner_delivers_readable_error(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("Output folder could not be verified")

    monkeypatch.setattr(runner.agent, "verify_project", fail)
    results = []

    thread = runner.start_verification(
        "doc.md", "view.md", str(tmp_path), lambda _: None, results.append
    )
    thread.join(timeout=1)

    assert results == [
        {"error": "Output folder could not be verified", "verification": True}
    ]
