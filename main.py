import tkinter as tk
from tkinter import ttk


def main():
    root = tk.Tk()
    root.title("Code Agent")
    root.geometry("680x360")
    root.minsize(560, 320)

    content = ttk.Frame(root, padding=20)
    content.pack(fill="both", expand=True)
    content.columnconfigure(1, weight=1)

    ttk.Label(content, text="Code Agent", font=("Segoe UI", 18, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 18)
    )

    api_key = tk.StringVar()
    documentation_path = tk.StringVar()
    views_path = tk.StringVar()
    output_directory = tk.StringVar()

    fields = [
        ("DeepSeek API key", api_key, True),
        ("Architecture documentation", documentation_path, False),
        ("Architecture views", views_path, False),
        ("Output directory", output_directory, False),
    ]

    for row, (label, value, is_secret) in enumerate(fields, start=1):
        ttk.Label(content, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 16), pady=7
        )
        entry = ttk.Entry(content, textvariable=value, show="*" if is_secret else "")
        entry.grid(row=row, column=1, sticky="ew", pady=7)

    ttk.Label(content, text="Choose the input files and output folder to begin.").grid(
        row=5, column=0, columnspan=2, sticky="w", pady=(18, 0)
    )

    root.mainloop()


if __name__ == "__main__":
    main()