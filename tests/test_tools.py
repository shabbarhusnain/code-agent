from pathlib import Path

import pytest

from src.code_agent.tools import Workspace


def test_write_then_read_creates_nested_directories(tmp_path):
    workspace = Workspace(tmp_path / "workspace")

    assert workspace.write_file("nested/deeper/note.txt", "hello") == (
        "Wrote nested/deeper/note.txt"
    )
    assert (tmp_path / "workspace" / "nested" / "deeper").is_dir()
    assert workspace.read_file("nested/deeper/note.txt") == "hello"


@pytest.mark.parametrize("path", ["../evil.txt", str(Path("/tmp") / "evil.txt")])
def test_workspace_blocks_paths_outside_its_root(tmp_path, path):
    workspace = Workspace(tmp_path / "workspace")

    with pytest.raises(ValueError):
        workspace.write_file(path, "blocked")


def test_list_files_returns_sorted_portable_relative_paths(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    assert workspace.list_files() == "(empty)"

    workspace.write_file("z.txt", "z")
    workspace.write_file("nested/a.txt", "a")

    assert workspace.list_files() == "nested/a.txt\nz.txt"


def test_call_returns_errors_for_unknown_tools_and_bad_arguments(tmp_path):
    workspace = Workspace(tmp_path / "workspace")

    assert workspace.call("missing", {}) == "ERROR: Unknown tool: missing"
    assert workspace.call("read_file", {}).startswith("ERROR:")
    assert workspace.call("write_file", {"path": "x.txt"}).startswith("ERROR:")
