"""The tool-calling loop that turns architecture input into a project."""

import json
from pathlib import Path

from . import checker, config, llm, preprocess, tools


SYSTEM_PROMPT = "You are a code-generation agent. You receive structured JSON built from an architecture documentation and UML (PlantUML) views of a software system. Generate a complete, runnable Python project implementing it, using ONLY the provided tools: write_file, read_file, and list_files. First plan the project layout, then write every file. The output must include the project directory layout with full source code, a dependency manifest (requirements.txt), a README.md, test cases (pytest), and optionally a Dockerfile. Keep code consistent with the class, component, and sequence diagrams and the API contracts, data schemas, and requirement IDs in the documentation. When everything is written, reply with a short final summary and make NO further tool calls."


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


def _required_missing(files):
    missing = []
    if "README.md" not in files:
        missing.append("README.md")
    if "requirements.txt" not in files:
        missing.append("requirements.txt")
    if not any(path.startswith("tests/") for path in files):
        missing.append("at least one file under tests/")
    return missing


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


def _repair_message(problems, tests_passed, test_output):
    message = "Self-check found these problems:\n- " + "\n- ".join(problems)
    if tests_passed is False and test_output:
        message += "\n\nGenerated pytest output:\n" + test_output
    return message


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
    steps = repairs = reminders = 0
    finished = cancelled = False
    try:
        documentation = Path(doc_path).read_text(encoding="utf-8")
        views = Path(view_path).read_text(encoding="utf-8")
        agent_input = preprocess.build_agent_input(documentation, views)
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
            missing = _required_missing(files)
            problems = checker.check_project(workspace.root)
            if problems:
                safe_log("Self-check found: " + "; ".join(problems))
            else:
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
                finished = True
                break
            if problems and repairs < 2:
                repairs += 1
                messages.append(
                    {"role": "user", "content": _repair_message(problems, tests_passed, test_output)}
                )
                continue
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
        "missing": _required_missing(files),
        "problems": problems,
        "tests_passed": tests_passed,
    }
