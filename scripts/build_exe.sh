#!/usr/bin/env sh
# Reference command only: build the Windows .exe on Windows with build_exe.bat.
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CodeAgent --paths src --add-data "samples:samples" --collect-submodules openai --collect-data certifi main.py
