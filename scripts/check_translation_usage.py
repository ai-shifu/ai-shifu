#!/usr/bin/env python3
"""Check translation key usage across backend and frontend."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, Set
import argparse

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "src" / "i18n"
BACKEND_DIR = ROOT / "src" / "api"
COOK_WEB_DIR = ROOT / "src" / "cook-web" / "src"
WEB_DIR = ROOT / "src" / "web" / "src"

STRING_LITERAL = re.compile(r"['\"][^'\"]+['\"]")

BACKEND_PATTERNS = [
    re.compile(r"_\(\s*['\"]([A-Z0-9_.]+)['\"]"),
    re.compile(r"raise_error\(\s*['\"]([A-Z0-9_.]+)['\"]"),
    re.compile(r"ERROR_CODE\\\[\"([A-Z0-9_.]+)\"\\\]"),
]

FRONTEND_PATTERNS = [
    re.compile(r"\bt\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"i18n\.t\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
]


def iter_locale_dirs() -> Iterable[Path]:
    if not I18N_DIR.exists():
        raise RuntimeError(f"Translation directory not found: {I18N_DIR}")
    for entry in sorted(I18N_DIR.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            yield entry


def flatten_translation(data, namespace: str) -> Dict[str, str]:
    if isinstance(data, dict):
        items: Dict[str, str] = {}
        flat_section = data.get("__flat__")
        if isinstance(flat_section, dict):
            for key, value in flat_section.items():
                if not isinstance(value, str):
                    raise ValueError(f"Translation value for '{key}' must be a string")
                composite_key = f"{namespace}.{key}" if namespace else key
                items[composite_key] = value
        for key, value in data.items():
            if key in {"__flat__", "__namespace__"}:
                continue
            next_namespace = f"{namespace}.{key}" if namespace else key
            items.update(flatten_translation(value, next_namespace))
        return items
    if not isinstance(data, str):
        raise ValueError(f"Translation value for '{namespace}' must be a string")
    return {namespace: data}


def collect_defined_keys() -> Set[str]:
    locale_dirs = list(iter_locale_dirs())
    if not locale_dirs:
        return set()
    reference_locale = locale_dirs[0]
    defined: Set[str] = set()
    for file_path in reference_locale.rglob("*.json"):
        rel = file_path.relative_to(reference_locale)
        namespace = str(rel.with_suffix("")).replace("/", ".")
        data = json.loads(file_path.read_text(encoding="utf-8"))
        declared_namespace = data.get("__namespace__")
        base_namespace = (
            declared_namespace
            if isinstance(declared_namespace, str) and declared_namespace
            else namespace
        )
        defined.update(flatten_translation(data, base_namespace).keys())
    return defined


def collect_backend_keys() -> Set[str]:
    patterns = BACKEND_PATTERNS
    used: Set[str] = set()
    for file_path in BACKEND_DIR.rglob("*.py"):
        if file_path.suffix != ".py":
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            for match in pattern.findall(text):
                if "." in match:
                    used.add(match)
    return used


def collect_frontend_keys() -> Set[str]:
    patterns = FRONTEND_PATTERNS
    used: Set[str] = set()
    extensions = (".ts", ".tsx", ".js", ".jsx")
    if COOK_WEB_DIR.exists():
        for file_path in COOK_WEB_DIR.rglob("*"):
            if file_path.suffix not in extensions:
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in patterns:
                for match in pattern.findall(text):
                    used.add(match)
    return used


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate translation key usage across backend and frontend."
    )
    parser.add_argument(
        "--fail-on-unused",
        action="store_true",
        help="Exit with non-zero status when unused keys are detected.",
    )
    parser.add_argument(
        "--unused-allowlist",
        type=Path,
        help="Path to a file listing unused keys that are temporarily allowed.",
    )
    return parser.parse_args()


def load_allowlist(path: Path | None) -> Set[str]:
    if not path:
        return set()

    if not path.exists():
        raise FileNotFoundError(f"Unused allowlist file not found: {path}")

    allowed: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        allowed.add(stripped)
    return allowed


def main() -> int:
    args = parse_args()
    defined_keys = collect_defined_keys()
    backend_used = collect_backend_keys()
    frontend_used = collect_frontend_keys()
    used_keys = backend_used | frontend_used

    missing_keys = sorted(k for k in used_keys if k not in defined_keys)
    unused_keys_all = sorted(k for k in defined_keys if k not in used_keys)
    allowlist = load_allowlist(args.unused_allowlist)
    unused_keys = [key for key in unused_keys_all if key not in allowlist]
    allowed_unused = [key for key in unused_keys_all if key in allowlist]

    if missing_keys:
        print("Missing translation keys detected:")
        for key in missing_keys:
            print(f" - {key}")
    else:
        print("No missing translation keys detected.")

    if unused_keys:
        print("\nUnused translation keys detected (consider cleanup):")
        for key in unused_keys:
            print(f" - {key}")
    else:
        if allowed_unused:
            print("\nOnly allowlisted unused translation keys detected:")
            for key in allowed_unused:
                print(f" - {key}")
        else:
            print("\nNo unused translation keys detected.")

    if missing_keys:
        return 1

    if args.fail_on_unused and unused_keys:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
