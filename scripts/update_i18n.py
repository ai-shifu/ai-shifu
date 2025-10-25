#!/usr/bin/env python3
"""Update shared i18n JSON files based on key usage across backend and frontends.

Default behavior:
- Scans src/api (Flask) and src/cook-web + src/web (React/Next.js) for translation key usage
- Computes keys missing from src/i18n across locales
- For namespaces that already exist (based on en-US mapping), inserts placeholder values for missing keys
- Does NOT prune by default; use --prune-unused to remove keys not referenced in code

Notes:
- Requires namespaces to already be declared and mapped to files. To add a new namespace, use scripts/create_translation_namespace.py first.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "src" / "i18n"
BACKEND_DIR = ROOT / "src" / "api"
COOK_WEB_DIR = ROOT / "src" / "cook-web"
WEB_DIR = ROOT / "src" / "web"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_translation(data, namespace: str) -> Dict[str, str]:
    def _flatten(obj, prefix: str, acc: Dict[str, str]):
        if isinstance(obj, dict):
            flat_section = obj.get("__flat__")
            if isinstance(flat_section, dict):
                for k, v in flat_section.items():
                    if isinstance(v, str):
                        acc[f"{namespace}.{k}" if namespace else k] = v
            for k, v in obj.items():
                if k in {"__flat__", "__namespace__"}:
                    continue
                next_prefix = f"{prefix}.{k}" if prefix else k
                _flatten(v, next_prefix, acc)
        else:
            if isinstance(obj, str) and prefix:
                acc[prefix] = obj
        return acc

    return _flatten(data, namespace, {})


def collect_defined_keys() -> Tuple[Dict[str, Path], Set[str]]:
    """Return (namespace_to_relpath, defined_keys_set) using en-US as reference for mapping."""
    if not I18N_DIR.exists():
        raise FileNotFoundError(f"Shared i18n directory not found: {I18N_DIR}")
    # Choose en-US as mapping reference
    mapping: Dict[str, Path] = {}
    defined: Set[str] = set()
    ref_dir = I18N_DIR / "en-US"
    if not ref_dir.exists():
        # fallback to first available
        candidates = [
            d for d in I18N_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]
        if not candidates:
            return mapping, defined
        ref_dir = candidates[0]

    for file_path in ref_dir.rglob("*.json"):
        if file_path.name.startswith("."):
            continue
        rel = file_path.relative_to(ref_dir)
        data = load_json(file_path)
        declared = data.get("__namespace__")
        ns = (
            declared
            if isinstance(declared, str) and declared
            else str(rel.with_suffix("")).replace("/", ".")
        )
        mapping[ns] = rel  # path under each locale dir
        defined.update(flatten_translation(data, ns).keys())

    # Load other locales to add their keys to defined set
    for locale_dir in [
        d for d in I18N_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]:
        for file_path in locale_dir.rglob("*.json"):
            if file_path.name.startswith("."):
                continue
            rel = file_path.relative_to(locale_dir)
            data = load_json(file_path)
            declared = data.get("__namespace__")
            ns = (
                declared
                if isinstance(declared, str) and declared
                else str(rel.with_suffix("")).replace("/", ".")
            )
            defined.update(flatten_translation(data, ns).keys())

    return mapping, defined


def load_metadata_namespaces() -> Set[str]:
    meta_path = I18N_DIR / "locales.json"
    if not meta_path.exists():
        return set()
    try:
        data = load_json(meta_path)
        items = data.get("namespaces") or []
        return {ns for ns in items if isinstance(ns, str) and ns}
    except Exception:
        return set()


# Regex patterns similar to scripts/check_translation_usage.py
FRONTEND_PATTERNS = [
    re.compile(r"\bt\s*\(\s*['\"]([a-zA-Z0-9_.-]+(?:\.[a-zA-Z0-9_.-]+)+)['\"][^)]*\)")
]
BACKEND_PATTERNS = [
    re.compile(r"_\(\s*['\"]([a-zA-Z0-9_.-]+)['\"]\s*\)"),
]


def collect_frontend_keys() -> Set[str]:
    used: Set[str] = set()
    extensions = {".ts", ".tsx", ".js", ".jsx"}
    for root in (COOK_WEB_DIR, WEB_DIR):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix not in extensions:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in FRONTEND_PATTERNS:
                for m in pat.findall(text):
                    used.add(m)
    return used


def collect_backend_keys() -> Set[str]:
    used: Set[str] = set()
    for path in BACKEND_DIR.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in BACKEND_PATTERNS:
            for m in pat.findall(text):
                used.add(m)
    return used


def set_nested(obj: dict, segments: List[str], value: str) -> None:
    cur = obj
    for seg in segments[:-1]:
        if not isinstance(cur.get(seg), dict):
            cur[seg] = {}
        cur = cur[seg]
    leaf = segments[-1]
    if leaf not in cur:
        cur[leaf] = value


def prune_unused(obj: dict, valid: Set[str], prefix: str) -> dict:
    # Remove keys whose full path (prefix.path) not in valid
    if not isinstance(obj, dict):
        return obj
    out: dict = {}
    for k, v in obj.items():
        if k in {"__namespace__", "__flat__"}:
            out[k] = v
            continue
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            pruned = prune_unused(v, valid, full)
            # Keep if any descendant remains or it is valid itself
            if pruned or full in valid:
                out[k] = pruned
        else:
            if full in valid:
                out[k] = v
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update shared i18n JSON based on usage across api and cook-web."
    )
    parser.add_argument(
        "--prune-unused",
        action="store_true",
        help="Remove keys not referenced in code (scoped to declared namespaces)",
    )
    args = parser.parse_args()

    ns_to_rel, defined = collect_defined_keys()
    allowed_namespaces = load_metadata_namespaces()
    backend_keys = collect_backend_keys()
    frontend_keys = collect_frontend_keys()
    used_all = backend_keys | frontend_keys

    # filter to declared namespaces
    def in_scope(key: str) -> bool:
        return any(key == ns or key.startswith(ns + ".") for ns in allowed_namespaces)

    used = {k for k in used_all if in_scope(k)}

    missing = sorted(k for k in used if k not in defined)
    if not missing and not args.prune_unused:
        print("No missing keys; nothing to update.")
        return 0

    # Prepare per-namespace patches
    ns_to_keys: Dict[str, List[str]] = {}
    for key in missing:
        ns = key.split(".")[0] + "." + key.split(".")[1] if "." in key else key
        # Re-evaluate: namespace is up to the second segment for shapes like server.user.* or module.social.* or common.core.*
        parts = key.split(".")
        if len(parts) >= 2:
            ns = parts[0] + "." + parts[1]
        else:
            ns = parts[0]
        ns_to_keys.setdefault(ns, []).append(key)

    # Write patches into each locale
    for ns, keys in ns_to_keys.items():
        rel = ns_to_rel.get(ns)
        if not rel:
            print(
                f"[skip] Namespace '{ns}' not found in reference locale; create it first (scripts/create_translation_namespace.py)."
            )
            continue
        for locale_dir in [
            d for d in I18N_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]:
            file_path = locale_dir / rel
            file_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"__namespace__": ns}
            if file_path.exists():
                try:
                    data = load_json(file_path)
                    if not isinstance(data, dict):
                        data = {"__namespace__": ns}
                except Exception:
                    data = {"__namespace__": ns}
            # compute subkeys under ns
            for key in keys:
                # strip ns prefix + dot
                tail = key[len(ns) + 1 :] if key.startswith(ns + ".") else key
                if not tail:
                    continue
                segments = tail.split(".")
                placeholder = f"@{locale_dir.name}.{key}"
                set_nested(data, segments, placeholder)

            # Optionally prune
            if args.prune_unused:
                valid_for_file = {k for k in used if k.startswith(ns + ".")}
                data = prune_unused(data, valid_for_file, ns)

            file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"Updated {file_path}")

    print("i18n update complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
