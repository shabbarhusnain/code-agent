"""Parse architecture Markdown and PlantUML into JSON-serializable data."""

import json
import re


_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_FENCE = re.compile(r"^```([\w+-]*)\s*$")
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$")


def _table_cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_table(lines):
    if len(lines) < 2 or not _TABLE_SEPARATOR.match(lines[1]):
        return None

    columns = _table_cells(lines[0])
    rows = []
    for line in lines[2:]:
        cells = _table_cells(line)
        rows.append(
            {
                column: cells[index] if index < len(cells) else ""
                for index, column in enumerate(columns)
            }
        )
    return {"columns": columns, "rows": rows}


def parse_documentation(text):
    """Split documentation into heading sections, text, code, and tables."""
    sections = []
    current = {"title": "Preamble", "level": 0, "text": [], "code_blocks": [], "tables": []}
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        fence = _FENCE.match(line)
        heading = _HEADING.match(line)

        if fence:
            language = fence.group(1)
            body = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                body.append(lines[index])
                index += 1
            current["code_blocks"].append(
                {"lang": language, "code": "\n".join(body)}
            )
        elif heading:
            if current["level"] or current["text"] or current["code_blocks"] or current["tables"]:
                sections.append(current)
            current = {
                "title": heading.group(2).strip(),
                "level": len(heading.group(1)),
                "text": [],
                "code_blocks": [],
                "tables": [],
            }
        elif line.strip().startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            table = _parse_table(table_lines)
            if table:
                current["tables"].append(table)
            continue
        elif line.strip():
            current["text"].append(line.strip())

        index += 1

    if current["level"] or current["text"] or current["code_blocks"] or current["tables"]:
        sections.append(current)
    return sections


def parse_views(text):
    """Extract PlantUML fenced blocks and simple diagram element names."""
    diagrams = []
    current_view = None
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            current_view = line[3:].strip()

        if line.strip().lower() == "```plantuml":
            body = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                body.append(lines[index])
                index += 1

            source = "\n".join(body)
            start = re.search(r"@startuml(?:\s+(\S+))?", source)
            diagrams.append(
                {
                    "name": (
                        start.group(1)
                        if start and start.group(1)
                        else f"diagram{len(diagrams) + 1}"
                    ),
                    "view": current_view,
                    "classes": re.findall(r"^\s*class\s+(\w+)", source, re.M),
                    "participants": re.findall(
                        r"^\s*(?:participant|actor|node|artifact)\s+(\w+)",
                        source,
                        re.M,
                    ),
                    "source": source,
                }
            )
        index += 1

    return diagrams


def build_agent_input(documentation_text, views_text):
    return {
        "documentation": parse_documentation(documentation_text),
        "views": parse_views(views_text),
    }


def to_json(documentation_text, views_text):
    return json.dumps(
        build_agent_input(documentation_text, views_text),
        indent=2,
        ensure_ascii=False,
    )
