"""Safe, file-based tools exposed to the code-generation model."""

from pathlib import Path


class Workspace:
    """A directory sandbox for file operations requested by the model."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, path):
        candidate = Path(path)
        if candidate.is_absolute():
            raise ValueError("Absolute paths are not allowed.")

        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ValueError("Path escapes the workspace.") from error
        return resolved

    def write_file(self, path, content):
        """Write UTF-8 content to a workspace-relative path."""
        destination = self._path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return f"Wrote {Path(path).as_posix()}"

    def read_file(self, path):
        """Read a UTF-8 file from a workspace-relative path."""
        return self._path(path).read_text(encoding="utf-8")

    def list_files(self):
        """Return every workspace file as a sorted, portable relative path."""
        files = sorted(
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file() and path.resolve().is_relative_to(self.root)
        )
        return "\n".join(files) if files else "(empty)"

    def call(self, name, args):
        """Call an exposed tool while returning recoverable errors to the model."""
        tools = {
            "write_file": self.write_file,
            "read_file": self.read_file,
            "list_files": self.list_files,
        }
        try:
            tool = tools[name]
        except KeyError:
            return f"ERROR: Unknown tool: {name}"

        try:
            return str(tool(**args))
        except Exception as error:  # Tool errors are model-recoverable feedback.
            return f"ERROR: {error}"


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a UTF-8 file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative file path.",
                    },
                    "content": {"type": "string", "description": "File contents."},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative file path.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]
