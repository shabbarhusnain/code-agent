"""Locate bundled resources in source and PyInstaller builds."""

from pathlib import Path
import sys


def resource_path(relative):
    """Return a path below the source root or PyInstaller extraction directory."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parents[2]
    return base / relative
