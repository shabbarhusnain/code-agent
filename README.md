# Code Agent

Code Agent is a simplified, desktop code-generation agent inspired by Claude Code. It reads an `Architecture_Documentation.md` file and an `Architecture_View.md` file containing PlantUML views, then uses the DeepSeek API to generate a project that follows the stack and user workflows described in those inputs.

## Features

- Tkinter desktop interface for selecting the API key, two architecture inputs, and output folder.
- Markdown and PlantUML preprocessing into structured architecture data.
- A bounded DeepSeek tool-calling loop with safe workspace-only file tools.
- The official OpenAI-compatible DeepSeek API endpoint using model `deepseek-v4-pro`.
- Required-deliverable checks, Python syntax/import checks, up to two repair rounds, and generated pytest/npm test execution when a compatible runtime is available.
- Architecture-aware generation: documented web/graphical applications must include a real UI, not just backend APIs; browser applications must include an HTML entry page.
- Cancellation, progress logs, and a redacted `RUN_LOG.txt` in generated output.
- Windows executable packaging and GitHub Actions CI/release automation.

## Architecture

The preprocessor turns the documentation and PlantUML into structured JSON. The agent supplies that JSON to DeepSeek, which can only write, read, and list files inside the output workspace. The agent is instructed to follow the documented language and implement user-facing flows as working interfaces. The output is checked for a README, dependency manifest, tests, and—when the architecture describes a web app—an interactive HTML UI. Python syntax and likely undeclared imports are checked; Python projects run pytest and Node.js projects run their `npm test` script when those runtimes are available. Failed checks are sent back to the model for up to two repair rounds.

```mermaid
flowchart LR
    A[Architecture Markdown + PlantUML] --> B[preprocess]
    B --> C[Agent loop + workspace tools]
    C --> D[Generated project]
    D --> E[Requirement checks, tests, and optional repair]
    E --> F[Output folder]
```

## Run from source

1. Install Python and create an environment if desired.
2. Install dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

3. Start the desktop app:

   ```sh
   python main.py
   ```

4. Optionally verify packaged resources and imports without opening the GUI:

   ```sh
   python main.py --selftest
   ```

## Use the `.exe`

1. Start `CodeAgent.exe`.
2. Enter a DeepSeek API key.
3. The bundled `Architecture_Documentation.md` and `Architecture_View.md` samples are selected automatically; use **Browse...** to choose different files.
4. Select an existing output folder.
5. Click **Run**. The log tracks progress; **Cancel** requests a safe stop.

The app asks before writing into a non-empty output folder. When generation ends, use **Open output folder** to inspect the generated project and `RUN_LOG.txt`.

## Build the `.exe` locally on Windows

The Windows executable must be built on Windows. From a Windows shell with dependencies installed, run:

```bat
scripts\build_exe.bat
```

The resulting executable is `dist\CodeAgent.exe`. A reference shell command for non-Windows environments is in `scripts/build_exe.sh`, but it does not produce a Windows executable.

## Tests

Run the full test suite with:

```sh
python -m pytest -q
```

Tests use fake API clients and mocks; they do not make DeepSeek network requests.

## CI/CD

GitHub Actions runs tests on Ubuntu and Windows for every push and pull request. After tests pass, the Windows job builds `CodeAgent.exe`, runs it with `--selftest`, and uploads it as the `CodeAgent-windows` workflow artifact. For version tags matching `v*`, the release job downloads that artifact and attaches it to a GitHub Release.

Download the executable from a successful workflow run’s artifacts, or from the matching GitHub Release for a version tag.

## Project structure

```text
.
├── main.py
├── samples/
│   ├── Architecture_Documentation.md
│   └── Architecture_View.md
├── scripts/
│   ├── build_exe.bat
│   └── build_exe.sh
├── src/code_agent/
│   ├── agent.py
│   ├── checker.py
│   ├── config.py
│   ├── llm.py
│   ├── paths.py
│   ├── preprocess.py
│   ├── runner.py
│   └── tools.py
└── tests/
```

## Limitations

- A DeepSeek API key with sufficient account balance and internet connection are required for generation. HTTP 402 insufficient-balance errors are reported directly; add funds to the DeepSeek account before retrying.
- DeepSeek responses can take time; the log displays the current request step and the 120-second request timeout while waiting.
- Generated tests that require runtimes or declared packages missing from the local machine are reported as skipped, not as model failures. Install the generated project manifest and rerun the tests to verify them.
- Generated output quality depends on the model and the supplied architecture documents.
- The packaged executable is Windows-only. It is unsigned, so Windows SmartScreen may show a warning.
