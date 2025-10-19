#!/usr/bin/env python3
"""Generate a pseudo-locale (qps-ploc) from an existing locale.

Usage:
  python scripts/generate_pseudo_locale.py --source en-US --target qps-ploc [--overwrite]

The script walks src/i18n/<source> and writes transformed strings to src/i18n/<target>,
preserving directories and namespaces. Only JSON string values are transformed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "src" / "i18n"

ACCENT_MAP = str.maketrans(
    {
        "A": "Å",
        "B": "Ƀ",
        "C": "Ć",
        "D": "Đ",
        "E": "Ē",
        "F": "Ғ",
        "G": "Ǥ",
        "H": "Ħ",
        "I": "Į",
        "J": "Ĵ",
        "K": "Ķ",
        "L": "Ŀ",
        "M": "Μ",
        "N": "Ň",
        "O": "Ø",
        "P": "Ƥ",
        "Q": "Ɋ",
        "R": "Ř",
        "S": "Š",
        "T": "Ŧ",
        "U": "Ų",
        "V": "Ṽ",
        "W": "Ŵ",
        "X": "Ẋ",
        "Y": "Ŷ",
        "Z": "Ž",
        "a": "å",
        "b": "ƀ",
        "c": "ć",
        "d": "đ",
        "e": "ē",
        "f": "ƒ",
        "g": "ǥ",
        "h": "ħ",
        "i": "į",
        "j": "ĵ",
        "k": "ķ",
        "l": "ŀ",
        "m": "m",
        "n": "ň",
        "o": "ø",
        "p": "ƥ",
        "q": "ɋ",
        "r": "ř",
        "s": "š",
        "t": "ŧ",
        "u": "ų",
        "v": "ṽ",
        "w": "ŵ",
        "x": "ẋ",
        "y": "ŷ",
        "z": "ž",
    }
)


def pseudoize(s: str) -> str:
    # Surround to visually expand and help catch truncation
    return f"⟦{s.translate(ACCENT_MAP)}⟧"


def transform(obj):
    if isinstance(obj, str):
        return pseudoize(obj)
    if isinstance(obj, list):
        return [transform(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # Preserve __namespace__/__flat__ and nested structures
            out[k] = transform(v)
        return out
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="en-US")
    ap.add_argument("--target", default="qps-ploc")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    src = I18N / args.source
    dst = I18N / args.target
    if not src.exists():
        print(f"Source locale not found: {src}")
        return 1
    dst.mkdir(parents=True, exist_ok=True)

    for path in src.rglob("*.json"):
        rel = path.relative_to(src)
        out_path = dst / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not args.overwrite:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out = transform(data)
        out_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"Generated pseudo-locale '{args.target}' from '{args.source}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
