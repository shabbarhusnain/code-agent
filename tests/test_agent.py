from main import validate_inputs


def test_validate_inputs_accepts_markdown_files_and_existing_output(tmp_path):
    documentation = tmp_path / "Architecture_Documentation.md"
    views = tmp_path / "Architecture_View.md"
    output = tmp_path / "output"
    documentation.write_text("# Architecture", encoding="utf-8")
    views.write_text("## Views", encoding="utf-8")
    output.mkdir()

    assert validate_inputs("api-key", str(documentation), str(views), str(output)) is None


def test_validate_inputs_requires_api_key(tmp_path):
    assert validate_inputs(" ", "doc.md", "views.md", str(tmp_path)) == (
        "Enter a DeepSeek API key."
    )


def test_validate_inputs_rejects_missing_architecture_file(tmp_path):
    views = tmp_path / "views.md"
    views.write_text("views", encoding="utf-8")

    assert validate_inputs("api-key", str(tmp_path / "missing.md"), str(views),
                           str(tmp_path)) == (
        "Select a valid architecture documentation file."
    )


def test_validate_inputs_requires_markdown_files(tmp_path):
    documentation = tmp_path / "architecture.txt"
    views = tmp_path / "views.md"
    documentation.write_text("architecture", encoding="utf-8")
    views.write_text("views", encoding="utf-8")

    assert validate_inputs("api-key", str(documentation), str(views),
                           str(tmp_path)) == (
        "Architecture documentation must be a Markdown (.md) file."
    )


def test_validate_inputs_requires_existing_output_directory(tmp_path):
    documentation = tmp_path / "doc.md"
    views = tmp_path / "views.md"
    documentation.write_text("architecture", encoding="utf-8")
    views.write_text("views", encoding="utf-8")

    assert validate_inputs("api-key", str(documentation), str(views),
                           str(tmp_path / "missing")) == (
        "Select an existing output directory."
    )