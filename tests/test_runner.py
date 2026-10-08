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
