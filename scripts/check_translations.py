#!/usr/bin/env python3
"""Validate shared translation JSON files across locales."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterable

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "src" / "i18n"


class TranslationError(Exception):
    """Raised when translation validation fails."""


def iter_locale_dirs() -> Iterable[Path]:
    if not I18N_DIR.exists():
        raise TranslationError(f"Shared translation directory not found: {I18N_DIR}")

    for entry in sorted(I18N_DIR.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            yield entry


def load_json(path: Path) -> Dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise TranslationError(f"Failed to parse JSON: {path} ({exc})") from exc


def flatten_translation(data, namespace: str) -> Dict[str, str]:
    """Flatten nested translation JSON to dot-separated keys."""

    def _flatten(obj, prefix: str):
        items: Dict[str, str] = {}
        if isinstance(obj, dict):
            # __flat__ allows specifying exact keys without additional nesting
            flat_section = obj.get("__flat__")
            if isinstance(flat_section, dict):
                for key, value in flat_section.items():
                    if not isinstance(value, str):
                        raise TranslationError(
                            f"Translation value for '{key}' must be string."
                        )
                    items[key] = value

            for key, value in obj.items():
                if key in {"__flat__", "__namespace__"}:
                    continue
                next_prefix = f"{prefix}.{key}" if prefix else key
                items.update(_flatten(value, next_prefix))
        else:
            if not isinstance(obj, str):
                raise TranslationError(
                    f"Translation value for '{prefix}' must be string."
                )
            items[prefix] = obj
        return items

    return _flatten(data, namespace)


def validate_locale_files(locale_dirs: Iterable[Path]):
    files_per_locale: Dict[str, Dict[str, Path]] = {}
    flattened_per_locale: Dict[str, Dict[str, Dict[str, str]]] = {}

    for locale_dir in locale_dirs:
        files: Dict[str, Path] = {}
        flattened: Dict[str, Dict[str, str]] = {}

        for file_path in sorted(locale_dir.rglob("*.json")):
            rel = file_path.relative_to(locale_dir)
            namespace = str(rel.with_suffix(""))  # keep directory separators
            files[namespace] = file_path
            data = load_json(file_path)
            normalized_namespace = namespace.replace("/", ".")
            flattened[namespace] = flatten_translation(data, normalized_namespace)

        files_per_locale[locale_dir.name] = files
        flattened_per_locale[locale_dir.name] = flattened

    locales = sorted(files_per_locale.keys())
    reference_locale = locales[0]
    problems: list[str] = []

    reference_files = set(files_per_locale[reference_locale].keys())

    # Ensure every locale contains the same set of translation files
    for locale in locales[1:]:
        current_files = set(files_per_locale[locale].keys())
        missing = reference_files - current_files
        extra = current_files - reference_files
        if missing:
            problems.append(
                f"Locale '{locale}' missing translation files: {sorted(missing)}"
            )
        if extra:
            problems.append(
                f"Locale '{locale}' has extra translation files not in '{reference_locale}': {sorted(extra)}"
            )

    # Ensure the set of keys match for each translation file across locales
    for namespace in sorted(reference_files):
        reference_keys = flattened_per_locale[reference_locale][namespace]
        for locale in locales[1:]:
            locale_keys = flattened_per_locale[locale].get(namespace)
            if locale_keys is None:
                continue  # already reported missing file
            missing_keys = set(reference_keys) - set(locale_keys)
            extra_keys = set(locale_keys) - set(reference_keys)
            if missing_keys:
                problems.append(
                    f"Locale '{locale}' missing keys in '{namespace}': {sorted(missing_keys)}"
                )
            if extra_keys:
                problems.append(
                    f"Locale '{locale}' has extra keys in '{namespace}': {sorted(extra_keys)}"
                )

    if problems:
        message = "\n".join(
            ["Translation validation failed:"] + [f" - {p}" for p in problems]
        )
        raise TranslationError(message)


def main() -> int:
    try:
        locale_dirs = list(iter_locale_dirs())
        if not locale_dirs:
            raise TranslationError(f"No locale directories found under {I18N_DIR}")
        validate_locale_files(locale_dirs)
    except TranslationError as error:
        print(str(error), file=sys.stderr)
        return 1

    print("All translation files validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
