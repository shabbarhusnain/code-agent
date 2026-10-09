"""The tool-calling loop that turns architecture input into a project."""

import json
from pathlib import Path

from . import checker, config, llm, preprocess, tools


SYSTEM_PROMPT = """You are a software engineering agent. You receive structured JSON built
from architecture documentation and UML views. Implement the documented system as a
complete, runnable project using ONLY the provided tools: write_file, read_file, and
list_files.

Treat the architecture documents as the source of truth. Follow their specified
language, runtime, platform, architecture, APIs, data schemas, functional requirements,
and user workflows. Do not replace a specified stack with Python or substitute an API
only for a documented user-facing application.

First inspect all requirements and diagrams, then plan and implement the complete
project. If the requirements describe a web-based or graphical user experience, build
the actual usable interface, connect its controls to the implemented application
logic, and implement the described screens and user flow. A backend, API docs, or
static mockup alone is not a complete UI. For a web app, include a working entry page,
functional client-side interactions, any required backend, and clear local launch
instructions in the README.
For games, implement the complete described play loop, player input, feedback, score,
and end/replay flow where those features are part of the requirements; do not deliver
only game APIs or architecture scaffolding.

Include all source files, a dependency manifest appropriate to the chosen stack
(requirements.txt, package.json, or equivalent), a README with exact setup/run/test
commands, and tests covering key user workflows. Implement the requested scope rather
than adding unrelated infrastructure. Review the written files against the input
requirements, list them, and fix omissions or inconsistencies before declaring success.
When the complete project is written, reply with a short summary and make NO further
tool calls."""


def _message_for_history(message):
    """Keep all server-provided message fields when continuing the conversation."""
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if isinstance(message, dict):
        return message
    return {
        "role": getattr(message, "role", "assistant"),
        "content": getattr(message, "content", None),
        "tool_calls": getattr(message, "tool_calls", None),
    }


def _requires_browser_ui(agent_input):
    text = json.dumps(agent_input.get("documentation", [])).lower()
    browser_markers = (
        "web-based",
        "web based",
        "browser-based",
        "browser based",
        "web application",
        "web app",
        "frontend",
        "front-end",
    )
    return any(marker in text for marker in browser_markers)


def _required_missing(files, require_browser_ui=False):
    missing = []
    if "README.md" not in files:
        missing.append("README.md")
    if not {"requirements.txt", "package.json"}.intersection(files):
        missing.append("a dependency manifest (requirements.txt or package.json)")
    if not any(
        {"tests", "test"}.intersection(Path(path).parts)
        or Path(path).name.startswith("test.")
        for path in files
    ):
        missing.append("at least one project test file")
    if require_browser_ui and not any(path.lower().endswith(".html") for path in files):
        missing.append("a browser UI (.html file) required by the architecture")
    return missing


def _repair_message(problems, tests_passed, test_output):
    details = list(problems)
    if tests_passed is False:
        details.append("generated test suite failed")
    message = "Generated project validation failed:\n- " + "\n- ".join(details)
    if tests_passed is False and test_output:
        message += "\n\nGenerated test output:\n" + test_output
    return message


def _workspace_files(workspace):
    listing = workspace.list_files()
    if listing == "(empty)":
        return []
    return [
        path
        for path in listing.splitlines()
        if path != "RUN_LOG.txt"
        and ".pytest_cache" not in path.split("/")
        and "__pycache__" not in path.split("/")
        and not path.endswith(".pyc")
    ]


def _tool_result(workspace, tool_call):
    function = tool_call.function
    name = function.name
    try:
        arguments = json.loads(function.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be a JSON object")
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return name, "", f"ERROR: Invalid tool arguments: {error}"
    return name, str(arguments.get("path", "")), workspace.call(name, arguments)


def run_agent(api_key, doc_path, view_path, out_dir, log=print, cancel_event=None, client=None):
    """Generate a project from architecture documents through bounded tool calls."""
    workspace = tools.Workspace(out_dir)
    log_lines = []

    def safe_log(line):
        line = str(line).replace(api_key, "[redacted]") if api_key else str(line)
        log_lines.append(line)
        log(line)

    problems = []
    tests_passed = None
    require_browser_ui = False
    steps = repairs = reminders = 0
    finished = cancelled = False
    try:
        documentation = Path(doc_path).read_text(encoding="utf-8")
        views = Path(view_path).read_text(encoding="utf-8")
        agent_input = preprocess.build_agent_input(documentation, views)
        require_browser_ui = _requires_browser_ui(agent_input)
        client = client or llm.make_client(api_key)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(agent_input)},
        ]

        while steps < config.MAX_STEPS:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                safe_log("Agent cancelled.")
                break

            safe_log(
                f"Waiting for DeepSeek response (step {steps + 1}/{config.MAX_STEPS}; "
                f"request timeout {llm.REQUEST_TIMEOUT_SECONDS}s)..."
            )
            message = llm.chat(client, messages, tools=tools.TOOL_SCHEMAS)
            steps += 1
            messages.append(_message_for_history(message))
            content = getattr(message, "content", None)
            if content:
                safe_log(content)

            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                for tool_call in tool_calls:
                    name, path, result = _tool_result(workspace, tool_call)
                    safe_log(f"{name}({path})")
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                    )
                continue

            files = _workspace_files(workspace)
            missing = _required_missing(files, require_browser_ui)
            problems = checker.check_project(workspace.root)
            if require_browser_ui:
                problems.extend(checker.check_browser_ui(workspace.root))
            if missing:
                safe_log("Project is missing required deliverables: " + "; ".join(missing))
            if problems:
                safe_log("Self-check found: " + "; ".join(problems))
            elif not missing:
                safe_log("Self-check passed.")
            tests_passed, test_output = checker.run_generated_tests(workspace.root)
            if tests_passed is None:
                safe_log(test_output)
            elif tests_passed:
                safe_log("Generated tests passed.")
            else:
                safe_log("Generated tests failed.")

            if missing:
                if reminders < 2:
                    reminders += 1
                    messages.append(
                        {"role": "user", "content": "The workspace is missing: " + ", ".join(missing)}
                    )
                    continue
                safe_log("Generation is incomplete because required deliverables are still missing.")
                break
            if (problems or tests_passed is False) and repairs < 2:
                repairs += 1
                messages.append(
                    {"role": "user", "content": _repair_message(problems, tests_passed, test_output)}
                )
                continue
            if problems or tests_passed is False:
                safe_log("Generation is incomplete because validation checks are still failing.")
                break
            finished = True
            break
        else:
            safe_log(f"Agent reached the maximum of {config.MAX_STEPS} steps.")
    finally:
        (workspace.root / "RUN_LOG.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    files = _workspace_files(workspace)
    return {
        "files": files,
        "steps": steps,
        "finished": finished,
        "cancelled": cancelled,
        "missing": _required_missing(files, require_browser_ui),
        "problems": problems,
        "tests_passed": tests_passed,
    }
