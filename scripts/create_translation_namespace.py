#!/usr/bin/env python3
"""Create skeleton translation namespace files for all locales."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "src" / "i18n"
LOCALES_FILE = I18N_DIR / "locales.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "namespace",
        help="Namespace identifier (e.g. backend-example or learn.prompts)",
    )
    parser.add_argument(
        "--keys",
        nargs="*",
        default=None,
        help="Optional translation keys to bootstrap inside __flat__",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files if they already exist",
    )
    return parser.parse_args()


def iter_locale_dirs() -> List[Path]:
    if not I18N_DIR.exists():
        raise RuntimeError(f"Translation directory not found: {I18N_DIR}")

    locales = [entry for entry in I18N_DIR.iterdir() if entry.is_dir()]
    if not locales:
        raise RuntimeError(f"No locale directories present under {I18N_DIR}")
    return sorted(locales, key=lambda p: p.name)


def namespace_to_path(namespace: str) -> Path:
    relative = namespace.replace(".", "/").replace("\\", "/")
    return Path(relative)


def ensure_namespace_files(namespace: str, keys: List[str] | None, force: bool) -> None:
    relative_path = namespace_to_path(namespace)
    locale_dirs = iter_locale_dirs()

    payload = {"__flat__": {}}
    if keys:
        payload["__flat__"].update({key: "" for key in keys})

    for locale_dir in locale_dirs:
        target_path = (locale_dir / relative_path).with_suffix(".json")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() and not force:
            raise RuntimeError(f"Translation file already exists: {target_path}")
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    update_locales_metadata(namespace)


def update_locales_metadata(namespace: str) -> None:
    data = {"locales": {}, "namespaces": []}
    if LOCALES_FILE.exists():
        try:
            data = json.loads(LOCALES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # noqa: BLE001
            raise RuntimeError(f"Invalid JSON in {LOCALES_FILE}: {exc}") from exc

    namespaces = set(data.get("namespaces", []))
    namespaces.add(namespace)
    data["namespaces"] = sorted(namespaces)

    LOCALES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    try:
        ensure_namespace_files(args.namespace, args.keys, args.force)
    except RuntimeError as error:
        print(f"Error: {error}")
        return 1

    print(
        "Created translation namespace '{namespace}' for locales: {locales}".format(
            namespace=args.namespace,
            locales=", ".join(p.name for p in iter_locale_dirs()),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
