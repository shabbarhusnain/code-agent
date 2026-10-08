from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from main import validate_inputs
from src.code_agent import config
from src.code_agent.agent import run_agent


SAMPLES = Path(__file__).parents[1] / "samples"


@pytest.fixture(autouse=True)
def skip_generated_pytest(monkeypatch):
    """Keep agent-loop tests independent from a machine's Python installation."""
    monkeypatch.setattr("src.code_agent.checker.shutil.which", lambda _: None)


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


def run_with_samples(tmp_path, responses, **kwargs):
    return run_agent(
        "not-used",
        SAMPLES / "Architecture_Documentation.md",
        SAMPLES / "Architecture_View.md",
        tmp_path / "project",
        log=lambda _: None,
        client=FakeClient(responses),
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
                ]
            ),
            FakeMessage(content="Project complete."),
        ],
    )

    assert result["finished"] is True
    assert result["missing"] == []
    assert result["files"] == ["README.md", "requirements.txt", "tests/test_x.py"]


def test_agent_returns_tool_error_for_invalid_json_and_continues(tmp_path):
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call("bad", "write_file", "not-json")]),
            FakeMessage(content="Done."),
            FakeMessage(content="Still done."),
            FakeMessage(content="Finally done."),
        ]
    )
    result = run_agent(
        "not-used", SAMPLES / "Architecture_Documentation.md", SAMPLES / "Architecture_View.md",
        tmp_path / "project", log=lambda _: None, client=client,
    )

    tool_messages = [message for message in client.requests[1]["messages"] if message["role"] == "tool"]
    assert tool_messages[0]["content"].startswith("ERROR: Invalid tool arguments:")
    assert result["finished"] is True


def test_agent_reminds_model_once_then_accepts_missing_file_fix(tmp_path):
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call("1", "write_file", '{"path": "requirements.txt", "content": ""}')]),
            FakeMessage(content="Done."),
            FakeMessage(tool_calls=[tool_call("2", "write_file", '{"path": "README.md", "content": "# Ready"}')]),
            FakeMessage(tool_calls=[tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": ""}')]),
            FakeMessage(content="Finished."),
        ]
    )
    result = run_agent(
        "not-used", SAMPLES / "Architecture_Documentation.md", SAMPLES / "Architecture_View.md",
        tmp_path / "project", log=lambda _: None, client=client,
    )

    reminders = [
        message for request in client.requests for message in request["messages"]
        if message["role"] == "user" and message["content"].startswith("The workspace is missing:")
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


def test_agent_stops_at_configured_step_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_STEPS", 3)
    client = FakeClient(
        [FakeMessage(tool_calls=[tool_call(str(step), "list_files", "{}")]) for step in range(3)]
    )
    logs = []
    result = run_agent(
        "not-used", SAMPLES / "Architecture_Documentation.md", SAMPLES / "Architecture_View.md",
        tmp_path / "project", log=logs.append, client=client,
    )

    assert result["steps"] == 3
    assert result["finished"] is False
    assert "maximum of 3 steps" in logs[-1]


def test_agent_repairs_syntax_problem_after_self_check(tmp_path, monkeypatch):
    from src.code_agent import agent

    monkeypatch.setattr(agent.checker, "run_generated_tests", lambda _: (None, "skipped"))
    client = FakeClient(
        [
            FakeMessage(
                tool_calls=[
                    tool_call("1", "write_file", '{"path": "README.md", "content": "# Demo"}'),
                    tool_call("2", "write_file", '{"path": "requirements.txt", "content": "pytest"}'),
                    tool_call("3", "write_file", '{"path": "tests/test_x.py", "content": "def test_ok():\\n    assert True"}'),
                    tool_call("4", "write_file", '{"path": "app.py", "content": "def broken(:\\n"}'),
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
        if message["role"] == "user" and message["content"].startswith("Self-check found")
    ]
    assert repair_messages
    assert result["problems"] == []
    assert result["finished"] is True
    assert (tmp_path / "project" / "RUN_LOG.txt").is_file()
