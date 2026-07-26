#!/usr/bin/env python3
"""Compatibility entry point for the Twitch ad overlay backend (also the PyInstaller entry point)."""

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parent
SRC_DIR = APP_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from twitch_ad_overlay.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
