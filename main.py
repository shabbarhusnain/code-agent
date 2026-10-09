import os
import importlib
from pathlib import Path
import queue
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from src.code_agent.paths import resource_path
from src.code_agent.runner import start_run


def validate_inputs(api_key, documentation_path, views_path, output_directory):
    if not api_key.strip():
        return "Enter a DeepSeek API key."

    for label, path in (
        ("Architecture documentation", documentation_path),
        ("Architecture views", views_path),
    ):
        file_path = Path(path)
        if not path.strip() or not file_path.is_file():
            return f"Select a valid {label.lower()} file."
        if file_path.suffix.lower() != ".md":
            return f"{label} must be a Markdown (.md) file."

    directory = Path(output_directory)
    if not output_directory.strip() or not directory.is_dir():
        return "Select an existing output directory."

    return None


def default_sample_paths():
    """Return the bundled architecture sample paths."""
    return (
        str(resource_path("samples/Architecture_Documentation.md")),
        str(resource_path("samples/Architecture_View.md")),
    )


def selftest():
    """Verify imports and bundled sample resources without starting the GUI."""
    try:
        package = "src.code_agent"
        for module in (
            "config",
            "paths",
            "preprocess",
            "tools",
            "llm",
            "checker",
            "agent",
            "runner",
        ):
            importlib.import_module(f"{package}.{module}")
        from src.code_agent import preprocess

        documentation = resource_path("samples/Architecture_Documentation.md").read_text(
            encoding="utf-8"
        )
        views = resource_path("samples/Architecture_View.md").read_text(encoding="utf-8")
        preprocess.build_agent_input(documentation, views)
    except Exception as error:
        print(f"Self-test failed: {error}", file=sys.stderr)
        return 1
    return 0


def main():
    root = tk.Tk()
    root.title("Code Agent")
    root.geometry("760x650")
    root.minsize(620, 480)

    content = ttk.Frame(root, padding=20)
    content.pack(fill="both", expand=True)
    content.columnconfigure(1, weight=1)
    content.rowconfigure(7, weight=1)

    ttk.Label(content, text="Code Agent", font=("Segoe UI", 18, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 18)
    )

    api_key = tk.StringVar()
    sample_documentation, sample_views = default_sample_paths()
    documentation_path = tk.StringVar(value=sample_documentation)
    views_path = tk.StringVar(value=sample_views)
    output_directory = tk.StringVar()
    status = tk.StringVar(value="Idle")
    events = queue.Queue()
    running = {"thread": None, "cancel_event": None}
    input_widgets = []

    fields = [
        ("DeepSeek API key", api_key, True, None),
        ("Architecture documentation", documentation_path, False, "file"),
        ("Architecture views", views_path, False, "file"),
        ("Output directory", output_directory, False, "directory"),
    ]

    def choose_file(value):
        selected = filedialog.askopenfilename(
            title="Select architecture document",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if selected:
            value.set(selected)

    def choose_directory(value):
        selected = filedialog.askdirectory(title="Select output directory")
        if selected:
            value.set(selected)

    for row, (label, value, is_secret, picker) in enumerate(fields, start=1):
        ttk.Label(content, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 16), pady=7
        )
        entry = ttk.Entry(content, textvariable=value, show="*" if is_secret else "")
        entry.grid(row=row, column=1, sticky="ew", pady=7)
        input_widgets.append(entry)
        if picker == "file":
            button = ttk.Button(
                content, text="Browse...", command=lambda field=value: choose_file(field)
            )
            button.grid(row=row, column=2, padx=(8, 0), pady=7)
            input_widgets.append(button)
        elif picker == "directory":
            button = ttk.Button(
                content, text="Browse...", command=lambda field=value: choose_directory(field)
            )
            button.grid(row=row, column=2, padx=(8, 0), pady=7)
            input_widgets.append(button)

    ttk.Label(content, text="Status:").grid(row=5, column=0, sticky="w", pady=(12, 6))
    ttk.Label(content, textvariable=status).grid(
        row=5, column=1, columnspan=2, sticky="w", pady=(12, 6)
    )
    log_area = scrolledtext.ScrolledText(content, height=14, state="disabled", wrap="word")
    log_area.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(8, 10))

    def append_log(line):
        log_area.configure(state="normal")
        log_area.insert("end", f"{line}\n")
        log_area.see("end")
        log_area.configure(state="disabled")

    def set_running(value):
        state = "disabled" if value else "normal"
        for widget in input_widgets:
            widget.configure(state=state)
        validate_button.configure(state=state)
        run_button.configure(state=state)
        cancel_button.configure(state="normal" if value else "disabled")

    def check_inputs():
        error = validate_inputs(
            api_key.get(), documentation_path.get(), views_path.get(), output_directory.get()
        )
        if error:
            status.set("Error")
            messagebox.showerror("Check inputs", error, parent=root)
            return False
        status.set("Idle")
        messagebox.showinfo(
            "Inputs checked", "The API key and selected paths passed validation.", parent=root
        )
        return True

    def finish(result):
        set_running(False)
        if "error" in result:
            status.set("Error")
            append_log(f"Error: {result['error']}")
            return

        cancelled = result.get("cancelled", False)
        if cancelled:
            status.set("Cancelled")
        elif not result.get("finished", True):
            status.set("Incomplete")
        elif result.get("tests_passed") is None:
            status.set("Finished (tests not verified)")
        else:
            status.set("Finished")
        files = result.get("files", [])
        append_log(f"Wrote {len(files)} files to {output_directory.get()}")
        open_button.configure(state="normal")
        missing = result.get("missing", [])
        if missing:
            warning = "Missing required output: " + ", ".join(missing)
            append_log(warning)
            messagebox.showwarning("Incomplete project", warning, parent=root)

    def poll_events():
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == "log":
                    append_log(payload)
                else:
                    finish(payload)
        except queue.Empty:
            pass
        root.after(100, poll_events)

    def run():
        if not check_inputs():
            return
        output = Path(output_directory.get())
        if any(output.iterdir()) and not messagebox.askyesno(
            "Output folder is not empty",
            "The output folder already contains files. Continue and allow files to be overwritten?",
            parent=root,
        ):
            return

        status.set("Running")
        append_log("Starting agent run...")
        open_button.configure(state="disabled")
        set_running(True)
        thread, cancel_event = start_run(
            api_key.get(),
            documentation_path.get(),
            views_path.get(),
            output_directory.get(),
            lambda line: events.put(("log", line)),
            lambda result: events.put(("done", result)),
        )
        running["thread"] = thread
        running["cancel_event"] = cancel_event

    def cancel():
        cancel_event = running["cancel_event"]
        if cancel_event is not None:
            cancel_event.set()
            append_log("Cancellation requested...")

    def open_output_folder():
        output = output_directory.get()
        try:
            if os.name == "nt":
                os.startfile(output)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", output])
            else:
                raise RuntimeError("Opening folders is supported on Windows and macOS only.")
        except OSError as error:
            messagebox.showerror("Open output folder", str(error), parent=root)

    def close():
        cancel_event = running["cancel_event"]
        if cancel_event is not None:
            cancel_event.set()
        root.destroy()

    validate_button = ttk.Button(content, text="Validate inputs", command=check_inputs)
    validate_button.grid(row=6, column=0, sticky="ew", pady=(8, 0))
    run_button = ttk.Button(content, text="Run", command=run)
    run_button.grid(row=6, column=1, sticky="ew", padx=8, pady=(8, 0))
    cancel_button = ttk.Button(content, text="Cancel", command=cancel, state="disabled")
    cancel_button.grid(row=6, column=2, sticky="ew", pady=(8, 0))
    open_button = ttk.Button(
        content, text="Open output folder", command=open_output_folder, state="disabled"
    )
    open_button.grid(row=8, column=0, columnspan=3, sticky="ew")

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll_events)
    root.mainloop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    main()
