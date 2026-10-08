import sys

from src.code_agent.paths import resource_path


def test_resource_path_finds_source_resources():
    path = resource_path("samples/Architecture_Documentation.md")

    assert path.is_file()
    assert path.name == "Architecture_Documentation.md"


def test_resource_path_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resource_path("samples/input.md") == tmp_path / "samples" / "input.md"
