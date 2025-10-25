#!/usr/bin/env python3
"""Generate/refresh src/i18n/locales.json

- Updates locale labels from common/language.json
- Rebuilds the namespaces list by scanning JSON and honoring __namespace__
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "src" / "i18n"
LOCALES_FILE = I18N_DIR / "locales.json"


def collect_json_files(dir_path: Path) -> list[Path]:
    files: list[Path] = []
    for entry in sorted(dir_path.rglob("*.json")):
        # Ignore hidden files/dirs
        if any(part.startswith(".") for part in entry.relative_to(dir_path).parts):
            continue
        files.append(entry)
    return files


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if not I18N_DIR.exists():
        print(f"Shared i18n directory not found: {I18N_DIR}")
        return 1

    if LOCALES_FILE.exists():
        try:
            locales_meta = read_json(LOCALES_FILE)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to parse {LOCALES_FILE}: {exc}")
            return 1
    else:
        locales_meta = {"default": "en-US", "locales": {}}

    locale_dirs = [
        d
        for d in sorted(I18N_DIR.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    ]

    # Update labels from common/language.json
    for code_dir in locale_dirs:
        language_file = code_dir / "common" / "language.json"
        if not language_file.exists():
            continue
        data = read_json(language_file)
        label = data.get("name") or code_dir.name
        locales_meta.setdefault("locales", {})
        if code_dir.name not in locales_meta["locales"]:
            locales_meta["locales"][code_dir.name] = {"label": label, "rtl": False}
        else:
            locales_meta["locales"][code_dir.name]["label"] = label

    # Build namespaces from json files (prefer __namespace__ when present)
    namespaces: set[str] = set()
    for code_dir in locale_dirs:
        for file_path in collect_json_files(code_dir):
            try:
                data = read_json(file_path)
            except Exception:
                continue
            declared = data.get("__namespace__")
            if isinstance(declared, str) and declared:
                namespaces.add(declared)
            else:
                rel = str(file_path.relative_to(code_dir).with_suffix(""))
                namespaces.add(rel.replace("/", "."))

    locales_meta["namespaces"] = sorted(list(namespaces))

    LOCALES_FILE.write_text(
        json.dumps(locales_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Updated {LOCALES_FILE} with {len(namespaces)} namespaces and {len(locale_dirs)} locales."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
