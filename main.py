from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


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


def main():
    root = tk.Tk()
    root.title("Code Agent")
    root.geometry("680x360")
    root.minsize(560, 320)

    content = ttk.Frame(root, padding=20)
    content.pack(fill="both", expand=True)
    content.columnconfigure(1, weight=1)

    ttk.Label(content, text="Code Agent", font=("Segoe UI", 18, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 18)
    )

    api_key = tk.StringVar()
    documentation_path = tk.StringVar()
    views_path = tk.StringVar()
    output_directory = tk.StringVar()

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
        if picker == "file":
            ttk.Button(
                content, text="Browse...", command=lambda field=value: choose_file(field)
            ).grid(row=row, column=2, padx=(8, 0), pady=7)
        elif picker == "directory":
            ttk.Button(
                content,
                text="Browse...",
                command=lambda field=value: choose_directory(field),
            ).grid(row=row, column=2, padx=(8, 0), pady=7)

    status = tk.StringVar(value="Choose the input files and output folder to begin.")
    ttk.Label(content, textvariable=status).grid(
        row=5, column=0, columnspan=3, sticky="w", pady=(18, 8)
    )

    def check_inputs():
        error = validate_inputs(
            api_key.get(),
            documentation_path.get(),
            views_path.get(),
            output_directory.get(),
        )
        if error:
            status.set(error)
            messagebox.showerror("Check inputs", error, parent=root)
            return

        status.set("Inputs look good. Project generation is not available yet.")
        messagebox.showinfo(
            "Inputs checked",
            "The API key and selected paths passed validation.",
            parent=root,
        )

    ttk.Button(content, text="Validate inputs", command=check_inputs).grid(
        row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0)
    )

    root.mainloop()


if __name__ == "__main__":
    main()