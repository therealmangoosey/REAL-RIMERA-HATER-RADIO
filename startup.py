"""Dependency-safe launcher for the Rimera Hater Radio bot."""

import importlib.util
import os
import subprocess
import sys


REQUIRED = (
    ("discord", "discord.py"),
    ("requests", "requests"),
    ("yt_dlp", "yt-dlp"),
)


def missing_packages():
    return [package for module, package in REQUIRED if importlib.util.find_spec(module) is None]


def main():
    missing = missing_packages()
    if missing:
        print("Missing Python dependencies: " + ", ".join(missing))
        print("Install them with:")
        print(f"  {sys.executable} -m pip install -r requirements.txt")
        return 1

    os.execv(sys.executable, [sys.executable, "bot.py", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
