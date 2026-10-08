@echo off
REM Build this Windows .exe on Windows, not on macOS or Linux.
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CodeAgent --paths src --add-data "samples;samples" --collect-submodules openai --collect-data certifi main.py
