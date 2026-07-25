"""Validate machine-readable repository files and frontend DOM references."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "data"}


def included(path: Path) -> bool:
    return not IGNORED_PARTS.intersection(path.relative_to(ROOT).parts)


def main() -> None:
    json_files = [path for path in ROOT.rglob("*.json") if included(path)]
    yaml_files = [path for pattern in ("*.yml", "*.yaml") for path in ROOT.rglob(pattern) if included(path)]
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))
    for path in yaml_files:
        yaml.safe_load(path.read_text(encoding="utf-8"))

    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    html_ids = set(re.findall(r'\bid="([^"]+)"', html))
    referenced_ids = set(re.findall(r'byId\("([^"]+)"\)', javascript))
    missing = sorted(referenced_ids - html_ids)
    if missing:
        raise SystemExit(f"JavaScript references missing HTML ids: {', '.join(missing)}")

    print(
        f"Validated {len(json_files)} JSON files, {len(yaml_files)} YAML files, "
        f"and {len(referenced_ids)} frontend DOM references."
    )


if __name__ == "__main__":
    main()
