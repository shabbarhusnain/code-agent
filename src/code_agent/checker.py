"""In-process validation for generated Python projects."""

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def _requirements(root):
    requirements = root / "requirements.txt"
    if not requirements.is_file():
        return set()
    names = set()
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", ".")):
            continue
        match = re.match(r"[A-Za-z0-9_.-]+", line)
        if match:
            names.add(match.group(0).replace("-", "_").lower())
    return names


def _local_modules(root, python_files):
    modules = set()
    for path in python_files:
        relative = path.relative_to(root)
        if relative.name == "__init__.py":
            if relative.parts[:-1]:
                modules.add(relative.parts[0])
        else:
            modules.add(relative.parts[0] if len(relative.parts) > 1 else relative.stem)
    return modules


def _is_allowed_import(name, stdlib, local, requirements):
    root_name = name.split(".", 1)[0]
    normalised = root_name.replace("-", "_").lower()
    return root_name in stdlib or root_name in local or normalised in requirements


def check_project(out_dir):
    """Return syntax, required-file, and best-effort dependency problems."""
    root = Path(out_dir)
    problems = []
    if not (root / "README.md").is_file():
        problems.append("missing README.md")
    if not (root / "requirements.txt").is_file():
        problems.append("missing requirements.txt")
    tests_dir = root / "tests"
    if not tests_dir.is_dir() or not any(path.is_file() for path in tests_dir.rglob("*")):
        problems.append("no tests/ file")

    python_files = [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]
    requirements = _requirements(root)
    local = _local_modules(root, python_files)
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | set(sys.builtin_module_names)

    for path in python_files:
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except SyntaxError as error:
            problems.append(f"{relative}:{error.lineno}: {error.msg}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level or not node.module:
                    continue
                names = [node.module]
            else:
                continue
            for name in names:
                if not _is_allowed_import(name, stdlib, local, requirements):
                    problems.append(f"{relative}:{node.lineno}: unlisted import '{name}'")
    return problems


def run_generated_tests(out_dir, timeout=120):
    """Run generated tests with a system Python when one is available."""
    python = shutil.which("python") or shutil.which("py")
    if not python:
        return None, "skipped: no system Python"
    root = Path(out_dir)
    try:
        completed = subprocess.run(
            [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = (completed.stdout + completed.stderr).strip()
        ok = completed.returncode == 0
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or "") + (error.stderr or "")
        ok = False
        output = f"tests timed out after {timeout} seconds\n{output}"
    finally:
        _remove_test_artifacts(root)
    if len(output) > 4_000:
        output = output[:4_000] + "... [truncated]"
    return ok, output


def _remove_test_artifacts(root):
    """Best-effort cleanup of test artifacts inside a generated project."""
    try:
        for current, directories, _ in os.walk(root, onerror=lambda _: None):
            artifacts = [
                name for name in directories if name in {".pytest_cache", "__pycache__"}
            ]
            for name in artifacts:
                try:
                    shutil.rmtree(Path(current) / name)
                except OSError:
                    pass
            directories[:] = [name for name in directories if name not in artifacts]
    except Exception:
        pass
