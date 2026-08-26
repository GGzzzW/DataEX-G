import sys
from pathlib import Path


def application_root() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root)
    return Path(__file__).resolve().parents[3]


def frontend_directory() -> Path:
    root = application_root()
    if getattr(sys, "frozen", False):
        return root / "frontend"
    return root / "frontend" / "dist"
