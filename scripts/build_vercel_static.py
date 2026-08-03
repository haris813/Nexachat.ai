"""Build the static Vercel frontend from the shared Flask assets."""

from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "public"


def main() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()
    shutil.copy2(PROJECT_ROOT / "templates" / "index.html", OUTPUT_DIR / "index.html")
    shutil.copytree(PROJECT_ROOT / "static", OUTPUT_DIR / "static")


if __name__ == "__main__":
    main()
