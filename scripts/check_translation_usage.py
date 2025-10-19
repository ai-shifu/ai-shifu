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
    re.compile(r"_\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"raise_error\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"raise_error_with_args\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"ERROR_CODE\\\[\"([A-Za-z0-9_.-]+)\"\\\]"),
]

FRONTEND_PATTERNS = [
    re.compile(r"\bt\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"i18n\.t\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"\bsetError\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
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


def load_metadata_namespaces() -> Set[str]:
    namespaces: Set[str] = set()
    meta = I18N_DIR / "locales.json"
    if not meta.exists():
        return namespaces
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        for ns in data.get("namespaces", []) or []:
            if isinstance(ns, str) and ns:
                namespaces.add(ns)
    except Exception:
        pass
    return namespaces


def collect_backend_keys() -> Set[str]:
    patterns = BACKEND_PATTERNS
    used: Set[str] = set()
    for file_path in BACKEND_DIR.rglob("*.py"):
        if file_path.suffix != ".py":
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            for match in pattern.findall(text):
                if "." not in match:
                    continue
                # Only consider our backend namespaces
                if match.startswith("server.") or match.startswith("module.backend."):
                    used.add(match)
                    # Add alias (with domain remap where needed)
                    if match.startswith("server."):
                        if match.startswith("server.shifu."):
                            tail = match[len("server.shifu.") :]
                            if tail in {
                                "courseNotFound",
                                "lessonCannotBeReset",
                                "lessonNotFound",
                                "lessonNotFoundInCourse",
                            }:
                                used.add("module.backend.course." + tail)
                        elif match.startswith("server.outline."):
                            used.add(
                                "module.backend.lesson."
                                + match[len("server.outline.") :]
                            )
                        elif match.startswith("server.outlineItem."):
                            used.add(
                                "module.backend.lesson."
                                + match[len("server.outlineItem.") :]
                            )
                        else:
                            used.add("module.backend." + match[len("server.") :])
                    else:
                        if match.startswith("module.backend.course."):
                            used.add(
                                "server.shifu." + match[len("module.backend.course.") :]
                            )
                        elif match.startswith("module.backend.lesson."):
                            t = match[len("module.backend.lesson.") :]
                            used.add("server.outline." + t)
                            used.add("server.outlineItem." + t)
                        else:
                            used.add("server." + match[len("module.backend.") :])
    return used


def collect_frontend_keys() -> Set[str]:
    patterns = FRONTEND_PATTERNS
    used: Set[str] = set()
    extensions = (".ts", ".tsx", ".js", ".jsx")
    for root in (COOK_WEB_DIR, WEB_DIR):
        if not root.exists():
            continue
        for file_path in root.rglob("*"):
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
    parser.add_argument(
        "--missing-allowlist",
        type=Path,
        help=(
            "Path to a file listing missing keys that are currently allowed. "
            "If provided, only missing keys not in this list will fail."
        ),
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
    defined_primary = collect_defined_keys()
    # Aliases for missing-key comparison only
    aliases: Set[str] = set()
    for key in list(defined_primary):
        if key.startswith("module.backend."):
            aliases.add("server." + key[len("module.backend.") :])
        elif key.startswith("server."):
            aliases.add("module.backend." + key[len("server.") :])
        # Domain rename aliases: course <-> shifu, lesson <-> outline/outlineItem
        if key.startswith("module.backend.course."):
            aliases.add("server.shifu." + key[len("module.backend.course.") :])
        if key.startswith("server.shifu."):
            aliases.add("module.backend.course." + key[len("server.shifu.") :])
        if key.startswith("module.backend.lesson."):
            tail = key[len("module.backend.lesson.") :]
            aliases.add("server.outline." + tail)
            aliases.add("server.outlineItem." + tail)
        if key.startswith("server.outline."):
            aliases.add("module.backend.lesson." + key[len("server.outline.") :])
        if key.startswith("server.outlineItem."):
            aliases.add("module.backend.lesson." + key[len("server.outlineItem.") :])
    defined_with_alias = set(defined_primary) | aliases
    backend_used = collect_backend_keys()
    frontend_used = collect_frontend_keys()
    used_keys = backend_used | frontend_used
    # Limit missing calculation to namespaces declared in shared metadata
    allowed_namespaces = load_metadata_namespaces()

    def in_scope(key: str) -> bool:
        return any(key == ns or key.startswith(ns + ".") for ns in allowed_namespaces)

    scoped_used = {k for k in used_keys if in_scope(k)}

    ignore_missing_prefixes = {
        "server.admin.",
    }
    ignore_missing_exact = {
        "server.common.imageRequired",
        "server.outline.isFirstScript",
        "server.outline.isLastScript",
        "server.outline.lessonNotFound",
        "server.outline.notFoundBeforeScript",
        "server.outline.scriptIdRequired",
        "server.outline.scriptNotFound",
    }
    missing_all = sorted(
        k
        for k in scoped_used
        if k not in defined_with_alias
        and not any(k.startswith(p) for p in ignore_missing_prefixes)
        and k not in ignore_missing_exact
    )
    unused_keys_all = sorted(k for k in defined_primary if k not in used_keys)
    allowlist = load_allowlist(args.unused_allowlist)
    unused_keys = [key for key in unused_keys_all if key not in allowlist]
    allowed_unused = [key for key in unused_keys_all if key in allowlist]
    missing_allow = load_allowlist(args.missing_allowlist)
    # Expand allowlist with alias keys to stabilize migration (server.* <-> module.backend.*)
    missing_allow_expanded: Set[str] = set(missing_allow)
    for key in list(missing_allow):
        if key.startswith("module.backend."):
            missing_allow_expanded.add("server." + key[len("module.backend.") :])
        elif key.startswith("server."):
            missing_allow_expanded.add("module.backend." + key[len("server.") :])
        # Domain aliasing for missing baseline
        if key.startswith("module.backend.course."):
            missing_allow_expanded.add(
                "server.shifu." + key[len("module.backend.course.") :]
            )
        if key.startswith("server.shifu."):
            missing_allow_expanded.add(
                "module.backend.course." + key[len("server.shifu.") :]
            )
        if key.startswith("module.backend.lesson."):
            t = key[len("module.backend.lesson.") :]
            missing_allow_expanded.add("server.outline." + t)
            missing_allow_expanded.add("server.outlineItem." + t)
        if key.startswith("server.outline."):
            missing_allow_expanded.add(
                "module.backend.lesson." + key[len("server.outline.") :]
            )
        if key.startswith("server.outlineItem."):
            missing_allow_expanded.add(
                "module.backend.lesson." + key[len("server.outlineItem.") :]
            )
    missing_keys = [key for key in missing_all if key not in missing_allow_expanded]
    allowed_missing = [key for key in missing_all if key in missing_allow_expanded]

    if missing_keys:
        print("Missing translation keys detected:")
        for key in missing_keys:
            print(f" - {key}")
    else:
        if allowed_missing:
            print("No new missing keys; allowed baseline present.")
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
