import tkinter as tk
from tkinter import ttk


def main():
    root = tk.Tk()
    root.title("Code Agent")
    root.geometry("480x240")
    root.minsize(400, 200)

    content = ttk.Frame(root, padding=24)
    content.pack(fill="both", expand=True)

    ttk.Label(content, text="Code Agent", font=("Segoe UI", 18, "bold")).pack(
        pady=(20, 12)
    )
    ttk.Label(content, text="Application started successfully.").pack()

    root.mainloop()


if __name__ == "__main__":
    main()