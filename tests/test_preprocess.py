import json
from pathlib import Path

from src.code_agent.preprocess import (
    build_agent_input,
    parse_documentation,
    parse_views,
    to_json,
)


SAMPLES_DIR = Path(__file__).parents[1] / "samples"


def test_parse_documentation_extracts_sections_code_and_tables():
    text = """# A. Overview
Architecture summary.
| Requirement | Component |
| --- | --- |
| FR-1 | Game |
```python
print("ready")
```
"""

    sections = parse_documentation(text)

    assert len(sections) == 1
    assert sections[0]["title"] == "A. Overview"
    assert sections[0]["level"] == 1
    assert sections[0]["text"] == ["Architecture summary."]
    assert sections[0]["tables"][0]["rows"] == [
        {"Requirement": "FR-1", "Component": "Game"}
    ]
    assert sections[0]["code_blocks"] == [
        {"lang": "python", "code": 'print("ready")'}
    ]


def test_sample_documentation_contains_all_sections_and_traceability_row():
    documentation = (SAMPLES_DIR / "Architecture_Documentation.md").read_text(
        encoding="utf-8"
    )

    sections = parse_documentation(documentation)
    titles = [section["title"] for section in sections]

    assert titles == [f"{letter}. {title}" for letter, title in (
        ("A", "Executive Summary"),
        ("B", "Traceability & Rationale"),
        ("C", "Architecture Overview"),
        ("D", "Detailed Technical Design"),
        ("E", "Operations & Deployment"),
        ("F", "Security Design"),
        ("G", "Observability & SRE"),
        ("H", "Testing Strategy"),
        ("I", "Migration, Data Conversion & Rollout Plan"),
        ("J", "Tradeoffs & Alternatives"),
        ("K", "Open Questions & Assumptions"),
        ("L", "Deliverables"),
    )]

    traceability = next(
        section for section in sections if section["title"].startswith("B.")
    )
    traceability_rows = traceability["tables"][0]["rows"]
    assert any(row["Requirement ID"] == "FR-1" for row in traceability_rows)


def test_parse_views_extracts_named_plantuml_diagram():
    text = """## Logic View
```plantuml
@startuml GameDiagram
class Game
participant Player
@enduml
```
"""

    assert parse_views(text) == [
        {
            "name": "GameDiagram",
            "view": "Logic View",
            "classes": ["Game"],
            "participants": ["Player"],
            "source": "@startuml GameDiagram\nclass Game\nparticipant Player\n@enduml",
        }
    ]


def test_sample_views_contain_all_diagrams_and_output_shape():
    documentation = (SAMPLES_DIR / "Architecture_Documentation.md").read_text(
        encoding="utf-8"
    )
    views = (SAMPLES_DIR / "Architecture_View.md").read_text(encoding="utf-8")

    data = build_agent_input(documentation, views)

    assert len(data["documentation"]) == 12
    assert len(data["views"]) >= 11
    assert len(data["views"]) == 13
    assert all(
        set(diagram) == {"name", "view", "classes", "participants", "source"}
        for diagram in data["views"]
    )
    assert all(isinstance(diagram["classes"], list) for diagram in data["views"])
    assert all(
        isinstance(diagram["participants"], list) for diagram in data["views"]
    )


def test_agent_input_can_be_encoded_as_json():
    data = build_agent_input("# Design\nReady.", "## View\nNo diagram.")

    assert json.loads(to_json("# Design\nReady.", "## View\nNo diagram.")) == data
    assert set(data) == {"documentation", "views"}
