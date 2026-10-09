from pathlib import Path
from threading import Event, Thread
import time
from types import SimpleNamespace

import pytest

from main import default_sample_paths, validate_inputs
from src.code_agent import preprocess
from src.code_agent.agent import (
    SYSTEM_PROMPT,
    _required_missing,
    _requires_browser_ui,
    run_agent,
)


SAMPLES = Path(__file__).parents[1] / "samples"


def test_default_sample_paths_point_to_bundled_architecture_files():
    assert default_sample_paths() == (
        str(SAMPLES / "Architecture_Documentation.md"),
        str(SAMPLES / "Architecture_View.md"),
    )


def test_generation_prompt_requires_architecture_faithful_user_interfaces():
    assert "Do not replace a specified stack with Python" in SYSTEM_PROMPT
    assert "A backend, API docs, or" in SYSTEM_PROMPT
    assert "static mockup alone is not a complete UI" in SYSTEM_PROMPT
    assert "continue from" in SYSTEM_PROMPT
    assert "preserve working implementation" in SYSTEM_PROMPT
    assert "The files in the output workspace are the source of" in SYSTEM_PROMPT
    assert "truth after an interrupted run" in SYSTEM_PROMPT
    assert "complete described play loop" in SYSTEM_PROMPT
    assert "request_user_action" in SYSTEM_PROMPT
    assert "resume only after the user confirms" in SYSTEM_PROMPT


def test_sample_architecture_requires_a_browser_ui():
    documentation = SAMPLES / "Architecture_Documentation.md"
    views = SAMPLES / "Architecture_View.md"
    parsed = preprocess.build_agent_input(
        documentation.read_text(encoding="utf-8"),
        views.read_text(encoding="utf-8"),
    )

    assert _requires_browser_ui(parsed)
    assert "a browser UI (.html file) required by the architecture" in _required_missing(
        ["README.md", "requirements.txt", "tests/test_game.py"],
        require_browser_ui=True,
    )


def test_web_ui_requirement_is_detected_in_architecture_tables():
    assert _requires_browser_ui(
        {"documentation": [{"tables": [{"rows": [{"Requirement": "Build a web-based UI"}]}]}]}
    )


def test_verify_project_runs_local_checks_without_creating_output_files(
    tmp_path, monkeypatch
):
    from src.code_agent import agent

    docs = tmp_path / "Architecture_Documentation.md"
    views = tmp_path / "Architecture_View.md"
    docs.write_text(
        "# A. Overview\nThis is a web-based fraction game.\n",
        encoding="utf-8",
    )
    views.write_text("## Views\n", encoding="utf-8")
    output = tmp_path / "project"
    output.mkdir()
    (output / "README.md").write_text("# Game\n", encoding="utf-8")
    (output / "package.json").write_text(
        '{"scripts": {"test": "node --test test/"}}', encoding="utf-8"
    )
    (output / "index.html").write_text(
        '<button onclick="play()">Play</button>', encoding="utf-8"
    )
    (output / "test").mkdir()
    (output / "test" / "game.test.js").write_text("test", encoding="utf-8")
    monkeypatch.setattr(
        agent.checker, "run_generated_tests", lambda _: (None, "npm tests skipped")
    )
    monkeypatch.setattr(
        agent.llm, "make_client", lambda *_: pytest.fail("verification must not call DeepSeek")
    )
    logs = []

    result = agent.verify_project(docs, views, output, log=logs.append)

    assert result["finished"] is False
    assert result["tests_passed"] is None
    assert "index.html" in result["files"]
    assert "package.json" in result["files"]
    assert not (output / "RUN_LOG.txt").exists()
    assert any("no DeepSeek API request" in line for line in logs)


@pytest.fixture(autouse=True)
def mock_generated_test_success(monkeypatch):
    """Keep agent-loop tests independent from installed project runtimes."""
    monkeypatch.setattr(
        "src.code_agent.checker.run_generated_tests",
        lambda _: (True, "mock project tests passed"),
    )


class FakeMessage:
    def __init__(self, content=None, tool_calls=None, reasoning_content=None):
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content

    def model_dump(self, exclude_none=True):
        fields = {
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "reasoning_content": self.reasoning_content,
        }
        return {key: value for key, value in fields.items() if not exclude_none or value is not None}


def tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=next(self.responses))])


def run_with_samples(tmp_path, responses, client=None, **kwargs):
    return run_agent(
        "not-used",
        SAMPLES / "Architecture_Documentation.md",
        SAMPLES / "Architecture_View.md",
        tmp_path / "project",
        log=lambda _: None,
        client=client or FakeClient(responses),
        **kwargs,
    )


def test_validate_inputs_accepts_markdown_files_and_existing_output(tmp_path):
    documentation = tmp_path / "Architecture_Documentation.md"
    views = tmp_path / "Architecture_View.md"
    output = tmp_path / "output"
    documentation.write_text("# Architecture", encoding="utf-8")
    views.write_text("## Views", encoding="utf-8")
    output.mkdir()

    assert validate_inputs("api-key", str(documentation), str(views), str(output)) is None


def test_validate_inputs_requires_api_key(tmp_path):
    assert validate_inputs(" ", "doc.md", "views.md", str(tmp_path)) == (
        "Enter a DeepSeek API key."
    )


def test_validate_inputs_rejects_missing_architecture_file(tmp_path):
    views = tmp_path / "views.md"
    views.write_text("views", encoding="utf-8")

    assert validate_inputs("api-key", str(tmp_path / "missing.md"), str(views),
                           str(tmp_path)) == (
        "Select a valid architecture documentation file."
    )


def test_validate_inputs_requires_markdown_files(tmp_path):
    documentation = tmp_path / "architecture.txt"
    views = tmp_path / "views.md"
    documentation.write_text("architecture", encoding="utf-8")
    views.write_text("views", encoding="utf-8")

    assert validate_inputs("api-key", str(documentation), str(views),
                           str(tmp_path)) == (
        "Architecture documentation must be a Markdown (.md) file."
    )


def test_validate_inputs_requires_existing_output_directory(tmp_path):
    documentation = tmp_path / "doc.md"
    views = tmp_path / "views.md"
    documentation.write_text("architecture", encoding="utf-8")
    views.write_text("views", encoding="utf-8")

    assert validate_inputs("api-key", str(documentation), str(views),
                           str(tmp_path / "missing")) == (
        "Select an existing output directory."
    )


def test_agent_writes_required_project_files_and_finishes(tmp_path):
    result = run_with_samples(
        tmp_path,
        [
            FakeMessage(
                tool_calls=[
                    tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                    tool_call("2", "write_file", '{"path": "requirements.txt", "content": "pytest"}'),
                    tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": "def test_ok():\\n    assert True"}'),
                    tool_call("4", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
                ]
            ),
            FakeMessage(content="Project complete."),
        ],
    )

    assert result["finished"] is True
    assert result["missing"] == []
    assert result["files"] == [
        "README.md", "index.html", "requirements.txt", "tests/test_x.py"
    ]


def test_agent_returns_tool_error_for_invalid_json_and_continues(tmp_path):
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call("bad", "write_file", "not-json")]),
            FakeMessage(content="Done."),
            FakeMessage(
                tool_calls=[
                    tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                    tool_call("2", "write_file", '{"path": "requirements.txt", "content": "pytest"}'),
                    tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": "def test_ok():\\n    assert True"}'),
                    tool_call("4", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
                ]
            ),
            FakeMessage(content="Complete."),
        ]
    )
    logs = []
    result = run_agent(
        "not-used", SAMPLES / "Architecture_Documentation.md", SAMPLES / "Architecture_View.md",
        tmp_path / "project", log=logs.append, client=client,
    )

    tool_messages = [message for message in client.requests[1]["messages"] if message["role"] == "tool"]
    assert tool_messages[0]["content"].startswith("ERROR: Invalid tool arguments:")
    assert result["finished"] is True
    assert result["missing"] == []
    assert any("Project is missing required deliverables:" in line for line in logs)


def test_agent_keeps_repairing_missing_files_until_fixed(tmp_path):
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call("1", "write_file", '{"path": "requirements.txt", "content": ""}')]),
            FakeMessage(content="Done."),
            FakeMessage(tool_calls=[
                tool_call("2", "write_file", '{"path": "README.md", "content": "# Ready"}'),
                tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": ""}'),
                tool_call("4", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
            ]),
            FakeMessage(content="Finished."),
        ]
    )
    result = run_agent(
        "not-used", SAMPLES / "Architecture_Documentation.md", SAMPLES / "Architecture_View.md",
        tmp_path / "project", log=lambda _: None, client=client,
    )

    reminders = [
        message for request in client.requests for message in request["messages"]
        if message["role"] == "user" and message["content"].startswith("Required deliverables are missing:")
    ]
    assert len({id(message) for message in reminders}) == 1
    assert result["finished"] is True
    assert result["missing"] == []


def test_agent_stops_cleanly_when_cancelled(tmp_path):
    event = Event()
    event.set()

    result = run_with_samples(tmp_path, [], cancel_event=event)

    assert result["cancelled"] is True
    assert result["finished"] is False
    assert result["steps"] == 0


def test_user_action_tool_pauses_model_requests_until_user_confirms(tmp_path):
    action_requested = Event()
    allow_resume = Event()
    client = FakeClient(
        [
            FakeMessage(
                tool_calls=[
                    tool_call(
                        "action-1",
                        "request_user_action",
                        '{"title": "Install Node.js", "instructions": "Install Node and press OK."}',
                    )
                ]
            ),
            FakeMessage(
                tool_calls=[
                    tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                    tool_call("2", "write_file", '{"path": "package.json", "content": "{\\"scripts\\":{\\"test\\":\\"node --test\\"}}"}'),
                    tool_call("3", "write_file", '{"path": "tests/game.test.js", "content": "test"}'),
                    tool_call("4", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
                ]
            ),
            FakeMessage(content="Complete."),
        ]
    )
    results = []
    actions = []

    def wait_for_user(action):
        actions.append(action)
        action_requested.set()
        assert allow_resume.wait(timeout=1)
        return "Node.js installed."

    thread = Thread(
        target=lambda: results.append(
            run_with_samples(
                tmp_path,
                [],
                client=client,
                on_user_action=wait_for_user,
            )
        ),
        daemon=True,
    )
    thread.start()
    assert action_requested.wait(timeout=1)
    time.sleep(0.03)
    assert len(client.requests) == 1
    allow_resume.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert actions == [
        {"title": "Install Node.js", "instructions": "Install Node and press OK."}
    ]
    assert results[0]["finished"] is True
    tool_results = [
        message
        for message in client.requests[1]["messages"]
        if message["role"] == "tool"
    ]
    assert tool_results[0]["content"] == "Node.js installed."


def test_cancelling_during_user_action_does_not_send_another_model_request(tmp_path):
    cancel_event = Event()
    client = FakeClient(
        [
            FakeMessage(
                tool_calls=[
                    tool_call(
                        "action-1",
                        "request_user_action",
                        '{"title": "Manual step", "instructions": "Complete this step."}',
                    )
                ]
            )
        ]
    )

    def cancel_from_action(_):
        cancel_event.set()
        return "Cancelled."

    result = run_with_samples(
        tmp_path,
        [],
        client=client,
        cancel_event=cancel_event,
        on_user_action=cancel_from_action,
    )

    assert result["cancelled"] is True
    assert result["finished"] is False
    assert len(client.requests) == 1


@pytest.mark.parametrize(
    ("test_output", "expected_reason"),
    [
        (
            "npm tests skipped: Node.js/npm is not installed",
            "Node.js/npm is not installed",
        ),
        (
            "npm dependency install failed for 'supertest' (exit code 1)",
            "npm dependency install failed",
        ),
    ],
)
def test_test_prerequisite_failure_finishes_without_another_api_request(
    tmp_path, monkeypatch, test_output, expected_reason
):
    from src.code_agent import agent

    monkeypatch.setattr(
        agent.checker,
        "run_generated_tests",
        lambda _: (None, test_output),
    )
    responses = [
        FakeMessage(
            tool_calls=[
                tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                tool_call("2", "write_file", '{"path": "package.json", "content": "{\\"scripts\\":{\\"test\\":\\"node --test\\"}}"}'),
                tool_call("3", "write_file", '{"path": "tests/game.test.js", "content": "test"}'),
                tool_call("4", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
            ]
        ),
        FakeMessage(content="Complete."),
    ]
    actions = []
    fake_client = FakeClient(responses)
    result = run_with_samples(
        tmp_path,
        [],
        client=fake_client,
        on_user_action=lambda action: actions.append(action) or "Installed Node.js.",
    )

    assert result["finished"] is False
    assert result["tests_passed"] is None
    assert expected_reason in result["incomplete_reason"]
    assert actions == []
    assert len(fake_client.requests) == 2


def test_agent_repairs_syntax_problem_after_self_check(tmp_path, monkeypatch):
    from src.code_agent import agent

    monkeypatch.setattr(agent.checker, "run_generated_tests", lambda _: (True, "passed"))
    client = FakeClient(
        [
            FakeMessage(
                tool_calls=[
                    tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                    tool_call("2", "write_file", '{"path": "requirements.txt", "content": "pytest"}'),
                    tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": "def test_ok():\\n    assert True"}'),
                    tool_call("4", "write_file", '{"path": "app.py", "content": "def broken(:\\n"}'),
                    tool_call("6", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
                ]
            ),
            FakeMessage(content="Done."),
            FakeMessage(tool_calls=[tool_call("5", "write_file", '{"path": "app.py", "content": "def fixed():\\n    return 1\\n"}')]),
            FakeMessage(content="Fixed."),
        ]
    )
    result = run_agent(
        "not-used", SAMPLES / "Architecture_Documentation.md", SAMPLES / "Architecture_View.md",
        tmp_path / "project", log=lambda _: None, client=client,
    )

    repair_messages = [
        message for request in client.requests for message in request["messages"]
        if message["role"] == "user" and message["content"].startswith("Generated project validation failed")
    ]
    assert repair_messages
    assert result["problems"] == []
    assert result["finished"] is True
    assert (tmp_path / "project" / "RUN_LOG.txt").is_file()


def test_agent_repairs_failed_tests_before_marking_generation_complete(tmp_path, monkeypatch):
    from src.code_agent import agent

    test_results = iter([(False, "assert 1 == 2"), (True, "2 passed")])
    monkeypatch.setattr(agent.checker, "run_generated_tests", lambda _: next(test_results))
    client = FakeClient(
        [
            FakeMessage(
                tool_calls=[
                    tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                    tool_call("2", "write_file", '{"path": "requirements.txt", "content": "pytest"}'),
                    tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": "def test_ok():\\n    assert True"}'),
                    tool_call("4", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
                ]
            ),
            FakeMessage(content="Done."),
            FakeMessage(
                tool_calls=[
                    tool_call("5", "write_file", '{"path": "app.py", "content": "def play(): return True"}'),
                ]
            ),
            FakeMessage(content="Fixed."),
        ]
    )

    result = run_agent(
        "not-used", SAMPLES / "Architecture_Documentation.md", SAMPLES / "Architecture_View.md",
        tmp_path / "project", log=lambda _: None, client=client,
    )

    assert result["tests_passed"] is True
    assert result["finished"] is True
    assert any(
        message["role"] == "user"
        and "Generated test output" in message["content"]
        for request in client.requests
        for message in request["messages"]
    )


def test_agent_keeps_repairing_failed_tests_until_the_user_cancels(tmp_path, monkeypatch):
    from src.code_agent import agent

    cancel_event = Event()
    attempts = []

    def fail_until_cancelled(_):
        attempts.append(True)
        if len(attempts) == 3:
            cancel_event.set()
        return False, "test failed"

    monkeypatch.setattr(agent.checker, "run_generated_tests", fail_until_cancelled)
    responses = [
        FakeMessage(
            tool_calls=[
                tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                tool_call("2", "write_file", '{"path": "requirements.txt", "content": "pytest"}'),
                tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": "def test_ok():\\n    assert True"}'),
                tool_call("4", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
            ]
        )
    ]
    responses.extend(FakeMessage(content="Done.") for _ in range(3))
    result = run_with_samples(tmp_path, responses, cancel_event=cancel_event)

    assert result["tests_passed"] is False
    assert result["finished"] is False
    assert result["cancelled"] is True
    assert len(attempts) == 3


def test_agent_repairs_more_than_two_times_before_passing(tmp_path, monkeypatch):
    from src.code_agent import agent

    test_results = iter(
        [(False, "failure 1"), (False, "failure 2"), (False, "failure 3"), (True, "passed")]
    )
    monkeypatch.setattr(agent.checker, "run_generated_tests", lambda _: next(test_results))
    responses = [
        FakeMessage(
            tool_calls=[
                tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                tool_call("2", "write_file", '{"path": "requirements.txt", "content": "pytest"}'),
                tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": "def test_ok():\\n    assert True"}'),
                tool_call("4", "write_file", '{"path": "index.html", "content": "<button onclick=play()>Play</button>"}'),
            ]
        )
    ]
    responses.extend(FakeMessage(content="Keep repairing.") for _ in range(4))
    client = FakeClient(responses)

    result = run_with_samples(tmp_path, [], client=client)

    repair_messages = {
        id(message): message
        for request in client.requests
        for message in request["messages"]
        if message.get("role") == "user"
        and message.get("content", "").startswith("Generated project validation failed")
    }
    repair_count = len(repair_messages)
    assert repair_count == 3
    assert result["tests_passed"] is True
    assert result["finished"] is True
