"""In-process validation for generated Python and Node.js projects."""

import ast
from html.parser import HTMLParser
import json
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
    if not any((root / name).is_file() for name in ("requirements.txt", "package.json")):
        problems.append("missing dependency manifest (requirements.txt or package.json)")
    has_test_files = any(
        path.is_file()
        and (
            "tests" in path.relative_to(root).parts
            or "test" in path.relative_to(root).parts
            or path.name.startswith("test.")
        )
        for path in root.rglob("*")
    )
    if not has_test_files:
        problems.append("no project test files (tests/ or test/)")

    package_json = root / "package.json"
    javascript_files = [
        path
        for path in root.rglob("*")
        if path.suffix.lower() in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
        and "node_modules" not in path.parts
    ]
    if package_json.is_file() and javascript_files:
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            problems.append(f"invalid package.json: {error}")
        else:
            if not isinstance(package, dict):
                problems.append("package.json must contain a JSON object")
            elif not isinstance(package.get("scripts", {}), dict):
                problems.append("package.json scripts must be a JSON object")
            elif not package.get("scripts", {}).get("test"):
                problems.append("package.json is missing a test script")

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


class _PageFeatures(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = set()
        self.script_sources = []
        self.inline_script = False
        self.inline_handlers = False

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.inline_handlers = self.inline_handlers or any(
            name.lower() in {"onclick", "onchange", "oninput", "onsubmit"}
            for name, _ in attrs
        )
        if tag.lower() == "script":
            attributes = dict(attrs)
            source = attributes.get("src")
            if source:
                self.script_sources.append(source)
            else:
                self.inline_script = True


def check_browser_ui(out_dir):
    """Check that a documented browser application has an interactive HTML entry."""
    root = Path(out_dir)
    pages = list(root.rglob("*.html"))
    if not pages:
        return ["missing browser UI HTML page"]

    for page in pages:
        try:
            content = page.read_text(encoding="utf-8")
            parser = _PageFeatures()
            parser.feed(content)
        except (OSError, UnicodeError, ValueError):
            continue

        linked_scripts = []
        for source in parser.script_sources:
            source_path_text = source.split("?", 1)[0].split("#", 1)[0]
            if source_path_text.startswith("/"):
                source_path_text = source_path_text.lstrip("/")
                source_path = root / source_path_text
            else:
                source_path = page.parent / source_path_text
            source_path = source_path.resolve()
            try:
                source_path.relative_to(root.resolve())
                if source_path.is_file():
                    linked_scripts.append(source_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                continue

        script = "\n".join(linked_scripts)
        if parser.inline_script:
            script += "\n" + content
        has_controls = bool(parser.tags.intersection({"button", "form", "input", "select", "textarea"}))
        has_interaction = bool(
            parser.inline_handlers
            or
            re.search(
                r"\baddEventListener\s*\(|\bon(?:click|change|input|submit)\s*=|"
                r"\bon(?:Click|Change|Input|Submit)\s*=|"
                r"\b(fetch|XMLHttpRequest)\s*\(",
                script,
            )
        )
        if has_controls and has_interaction:
            return []

    return ["browser UI must include interactive controls wired to application behavior"]


def run_generated_tests(out_dir, timeout=120):
    """Run the available project test suites without installing dependencies."""
    root = Path(out_dir)
    python_files = [
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    ]
    package_json = root / "package.json"
    javascript_files = [
        path
        for path in root.rglob("*")
        if path.suffix.lower() in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
        and "node_modules" not in path.parts
    ]
    package = {}
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            package = {}

    results = []
    if python_files:
        python = shutil.which("python") or shutil.which("py")
        if not python:
            results.append((None, "pytest skipped: no system Python"))
        else:
            requirements = _requirements(root)
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
                missing_dependency = _missing_declared_test_dependency(output, requirements)
                if missing_dependency:
                    results.append(
                        (
                            None,
                            f"pytest skipped: declared dependency '{missing_dependency}' "
                            "is not installed; install requirements.txt to run tests",
                        )
                    )
                else:
                    results.append((completed.returncode == 0, output or "pytest completed"))
            except subprocess.TimeoutExpired as error:
                output = (error.stdout or "") + (error.stderr or "")
                results.append((False, f"pytest timed out after {timeout} seconds\n{output}"))
            finally:
                _remove_test_artifacts(root)

    if javascript_files and package.get("scripts", {}).get("test"):
        npm = find_npm()
        if not npm:
            results.append((None, "npm tests skipped: Node.js/npm is not installed"))
        else:
            command, use_shell = _npm_test_command(npm)
            try:
                completed = subprocess.run(
                    command,
                    cwd=root,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                    shell=use_shell,
                    env=_npm_environment(npm),
                )
                output = (completed.stdout + completed.stderr).strip()
                missing_dependency = _missing_node_dependency(output, package)
                if missing_dependency:
                    results.append(
                        (
                            None,
                            f"npm tests skipped: dependency '{missing_dependency}' is not "
                            "installed; run npm install before rerunning tests",
                        )
                    )
                else:
                    results.append((completed.returncode == 0, output or "npm test completed"))
            except subprocess.TimeoutExpired as error:
                output = (error.stdout or "") + (error.stderr or "")
                results.append((False, f"npm test timed out after {timeout} seconds\n{output}"))

    if not results:
        return None, "tests skipped: no supported Python or Node.js test suite found"

    outcomes = [passed for passed, _ in results]
    passed = False if False in outcomes else None if None in outcomes else True
    output = "\n\n".join(message for _, message in results)
    if len(output) > 4_000:
        output = output[:4_000] + "... [truncated]"
    return passed, output


def find_npm(windows=None):
    """Find npm on PATH or at common Windows installer locations."""
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm:
        return npm
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return None

    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "nodejs",
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        / "Programs"
        / "nodejs",
    ]
    for root in roots:
        for name in ("npm.cmd", "npm.exe"):
            candidate = root / name
            if candidate.is_file():
                return str(candidate)
    return None


def _missing_node_dependency(output, package):
    match = re.search(
        r"Cannot find (?:module|package) ['\"]([^'\"]+)['\"]", output
    )
    if not match:
        return None
    module = match.group(1).split("/", 1)[0]
    if module.startswith("@"):
        module = "/".join(match.group(1).split("/")[:2])
    dependencies = {
        **package.get("dependencies", {}),
        **package.get("devDependencies", {}),
    }
    return module if module in dependencies else None


def _npm_test_command(npm, windows=None):
    """Build a subprocess command that can launch npm's Windows .cmd shim."""
    if windows is None:
        windows = os.name == "nt"
    if windows:
        return f'"{npm}" test', True
    return [npm, "test"], False


def _npm_environment(npm):
    """Expose the adjacent node.exe to npm even if PATH predates installation."""
    environment = os.environ.copy()
    npm_directory = str(Path(npm).resolve().parent)
    current_path = environment.get("PATH", "")
    path_entries = current_path.split(os.pathsep)
    if not any(Path(entry).resolve() == Path(npm_directory) for entry in path_entries if entry):
        environment["PATH"] = os.pathsep.join(
            [npm_directory, current_path] if current_path else [npm_directory]
        )
    return environment


def _missing_declared_test_dependency(output, requirements):
    match = re.search(
        r"(?:ModuleNotFoundError|ImportError): No module named ['\"]([^'\"]+)['\"]",
        output,
    )
    if not match:
        return None
    module = match.group(1).split(".", 1)[0].replace("-", "_").lower()
    return module if module in requirements else None


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
