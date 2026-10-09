import json
import os
import shutil
import subprocess

import pytest

from src.code_agent import checker


def test_checker_reports_syntax_error_and_missing_readme(tmp_path):
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    problems = checker.check_project(tmp_path)

    assert "missing README.md" in problems
    assert any(problem.startswith("broken.py:1:") for problem in problems)


def test_generated_tests_are_skipped_without_system_python(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    monkeypatch.setattr(checker.shutil, "which", lambda _: None)

    assert checker.run_generated_tests(tmp_path) == (
        None,
        "pytest skipped: no system Python",
    )


def test_generated_tests_skip_for_non_python_project(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest"}}', encoding="utf-8")

    assert checker.run_generated_tests(tmp_path) == (
        None,
        "tests skipped: no supported Python or Node.js test suite found",
    )


def test_generated_tests_skip_when_a_declared_dependency_is_uninstalled(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("fastapi==1.0\npytest\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    monkeypatch.setattr(checker.shutil, "which", lambda _: "python")
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 4, "", "ModuleNotFoundError: No module named 'fastapi'"
        ),
    )

    passed, output = checker.run_generated_tests(tmp_path)

    assert passed is None
    assert "declared dependency 'fastapi' is not installed" in output


def test_project_checker_accepts_package_json_manifest(tmp_path):
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"name": "example", "scripts": {"test": "node --test tests/"}}',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_example.js").write_text("test", encoding="utf-8")

    assert checker.check_project(tmp_path) == []


def test_project_checker_accepts_singular_node_test_directory(tmp_path):
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "node --test test/"}}', encoding="utf-8"
    )
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "example.test.js").write_text("test", encoding="utf-8")
    (tmp_path / "server.js").write_text("pass", encoding="utf-8")

    assert checker.check_project(tmp_path) == []


def test_project_checker_reports_missing_node_test_script(tmp_path):
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"scripts": {}}', encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "example.test.js").write_text("test", encoding="utf-8")
    (tmp_path / "server.js").write_text("pass", encoding="utf-8")

    assert "package.json is missing a test script" in checker.check_project(tmp_path)


def test_generated_node_tests_run_through_npm_without_installing(
    tmp_path, monkeypatch
):
    package = {
        "scripts": {"test": "node --test tests/"},
        "devDependencies": {"example-test-runner": "1.0"},
    }
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "app.test.js").write_text("test", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        checker.shutil,
        "which",
        lambda name: "npm.cmd" if name in {"npm", "npm.cmd"} else None,
    )

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "2 tests passed", "")

    monkeypatch.setattr(checker.subprocess, "run", run)

    passed, output = checker.run_generated_tests(tmp_path)

    assert passed is True
    assert "2 tests passed" in output
    expected_command, expected_shell = checker._npm_test_command(
        "npm.cmd", windows=os.name == "nt"
    )
    assert calls[0][0] == expected_command
    assert calls[0][1]["shell"] is expected_shell
    assert calls[0][1]["cwd"] == tmp_path


@pytest.mark.parametrize(
    ("windows", "expected", "use_shell"),
    [
        (True, '"C:\\Program Files\\nodejs\\npm.cmd" test', True),
        (False, ["/usr/bin/npm", "test"], False),
    ],
)
def test_npm_test_command_supports_platform_launcher(windows, expected, use_shell):
    npm = "C:\\Program Files\\nodejs\\npm.cmd" if windows else "/usr/bin/npm"

    assert checker._npm_test_command(npm, windows=windows) == (expected, use_shell)


def test_generated_node_test_failures_are_reported_for_repair(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "node --test tests/"}}', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "app.test.js").write_text("test", encoding="utf-8")
    monkeypatch.setattr(checker.shutil, "which", lambda name: "npm" if name == "npm" else None)
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, "", "AssertionError: expected true"
        ),
    )

    passed, output = checker.run_generated_tests(tmp_path)

    assert passed is False
    assert "AssertionError" in output


def test_generated_node_tests_skip_when_npm_is_unavailable(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "node --test tests/"}}', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "app.test.js").write_text("test", encoding="utf-8")
    monkeypatch.setattr(checker.shutil, "which", lambda _: None)

    assert checker.run_generated_tests(tmp_path) == (
        None,
        "npm tests skipped: Node.js/npm is not installed",
    )


def test_generated_node_tests_report_missing_declared_dependencies(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(
        json.dumps({
            "scripts": {"test": "node --test tests/"},
            "dependencies": {"express": "1.0"},
        }),
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "app.test.js").write_text("test", encoding="utf-8")
    monkeypatch.setattr(checker.shutil, "which", lambda name: "npm" if name == "npm" else None)
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, "", "Error: Cannot find module 'express'"
        ),
    )

    passed, output = checker.run_generated_tests(tmp_path)

    assert passed is None
    assert "dependency 'express' is not installed" in output


def test_browser_ui_checker_accepts_interactive_game_page(tmp_path):
    (tmp_path / "index.html").write_text(
        '<button id="start">Play</button><script>'
        'document.querySelector("#start").addEventListener("click", startGame);'
        "</script>",
        encoding="utf-8",
    )

    assert checker.check_browser_ui(tmp_path) == []


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<h1>Static mockup</h1><button>Play</button>", "wired to application behavior"),
        ("<h1>No game page</h1>", "interactive controls"),
    ],
)
def test_browser_ui_checker_rejects_incomplete_page(tmp_path, html, expected):
    (tmp_path / "index.html").write_text(html, encoding="utf-8")

    assert expected in checker.check_browser_ui(tmp_path)[0]


def test_generated_tests_leave_no_cache_artifacts(tmp_path):
    if not (shutil.which("python") or shutil.which("py")):
        pytest.skip("no system Python")
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )

    checker.run_generated_tests(tmp_path)

    assert not list(tmp_path.rglob(".pytest_cache"))
    assert not list(tmp_path.rglob("__pycache__"))
