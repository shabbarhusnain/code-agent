import json

from src.code_agent.preprocess import (
    build_agent_input,
    parse_documentation,
    parse_views,
    to_json,
)


def test_parse_documentation_extracts_sections_code_and_tables():
    text = """Overview before the first heading.
# Design
Architecture summary.
| Requirement | Component |
| --- | --- |
| FR-1 | Game |
```python
print("ready")
```
"""

    sections = parse_documentation(text)

    assert sections[0]["title"] == "Preamble"
    assert sections[0]["text"] == ["Overview before the first heading."]
    design = sections[1]
    assert design["title"] == "Design"
    assert design["tables"][0]["rows"] == [
        {"Requirement": "FR-1", "Component": "Game"}
    ]
    assert design["code_blocks"] == [{"lang": "python", "code": 'print("ready")'}]


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


def test_agent_input_can_be_encoded_as_json():
    data = build_agent_input("# Design\nReady.", "## View\nNo diagram.")

    assert json.loads(to_json("# Design\nReady.", "## View\nNo diagram.")) == data
    assert set(data) == {"documentation", "views"}
