import shutil

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
    monkeypatch.setattr(checker.shutil, "which", lambda _: None)

    assert checker.run_generated_tests(tmp_path) == (None, "skipped: no system Python")


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
