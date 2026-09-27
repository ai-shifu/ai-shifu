#!/usr/bin/env python3
"""Check translation key usage across backend and frontend."""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "src" / "i18n"
BACKEND_DIR = ROOT / "src" / "api"
WEB_DIR = ROOT / "src" / "web" / "src"

KEY_LITERAL = re.compile(r"(['\"`])([A-Za-z0-9_.-]+)\1")
DYNAMIC_KEY_LITERAL = re.compile(
    r"(['\"`])([A-Za-z][A-Za-z0-9_.-]*\.(?:(?:\$\{[^}\n]*\}|\{[^}\n]*\})|[A-Za-z0-9_.-])+)\1"
)
TRANSLATION_KEY_LITERAL = re.compile(
    r"^(?:common|component|module|server)\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$"
)

BACKEND_PATTERNS = [
    re.compile(r"_\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"raise_error\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"raise_error_with_args\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"raise_param_error\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"ERROR_CODE\\\[\"([A-Za-z0-9_.-]+)\"\\\]"),
]

FRONTEND_PATTERNS = [
    re.compile(r"\bt\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"i18n\.t\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    re.compile(r"\bsetError\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
    # Support <Trans i18nKey='namespace.key'> usages in TSX/JSX
    re.compile(r"i18nKey\s*=\s*['\"]([A-Za-z0-9_.-]+)['\"]"),
]

USE_TRANSLATION_ALIAS_PATTERN = re.compile(
    r"""
    \{\s*t
    (?:\s*:\s*([A-Za-z_][A-Za-z0-9_]*))?
    [^}]*\}
    \s*=\s*useTranslation\(
      \s*(?:
        ['"]([A-Za-z0-9_.-]+)['"] |
        \[\s*['"]([A-Za-z0-9_.-]+)['"]
      )
    """,
    re.VERBOSE,
)


def translation_aliases(keys: set[str]) -> set[str]:
    """Include the shared backend namespace and domain compatibility aliases."""
    aliases = set(keys)
    for key in keys:
        if key.startswith("module.backend.course."):
            aliases.add("server.shifu." + key.removeprefix("module.backend.course."))
        elif key.startswith("module.backend.lesson."):
            tail = key.removeprefix("module.backend.lesson.")
            aliases.update({"server.outline." + tail, "server.outlineItem." + tail})
        elif key.startswith("module.backend."):
            aliases.add("server." + key.removeprefix("module.backend."))
        elif key.startswith("server.shifu."):
            aliases.add("module.backend.course." + key.removeprefix("server.shifu."))
        elif key.startswith(("server.outline.", "server.outlineItem.")):
            aliases.add("module.backend.lesson." + key.split(".", 2)[2])
        elif key.startswith("server."):
            aliases.add("module.backend." + key.removeprefix("server."))
    return aliases


def collect_frontend_relative_calls(text: str) -> dict[int, str]:
    """Locate first arguments of namespaced and forwarded translator calls."""
    declarations: dict[str, list[tuple[int, str]]] = {}
    for match in USE_TRANSLATION_ALIAS_PATTERN.finditer(text):
        alias = match.group(1) or "t"
        namespace = match.group(2) or match.group(3)
        declarations.setdefault(alias, []).append((match.start(), namespace))

    # t and translate are the existing forwarded-translator conventions. Hook
    # aliases are recognized explicitly rather than accepting arbitrary calls.
    forwarded_aliases = set(
        re.findall(
            r"\b(t[A-Z][A-Za-z0-9_]*|translate)\s*:\s*"
            r"(?:TFunction\b|Translation[A-Za-z0-9_]*\b|\(\s*key\s*:\s*string\b)",
            text,
        )
    )
    names = "|".join(
        re.escape(name)
        for name in sorted({"t", "translate"} | declarations.keys() | forwarded_aliases)
    )
    call_pattern = re.compile(rf"\b({names})\(\s*")
    argument_tokens = re.compile(
        r"(?P<quote>['\"`])(?:\\.|(?!(?P=quote)).)*(?P=quote)"
        r"|//[^\n]*|/\*.*?\*/|[(){}\[\],]",
        re.DOTALL,
    )
    calls: dict[int, str] = {}
    for match in call_pattern.finditer(text):
        alias = match.group(1)
        namespace = ""
        # A member call uses a forwarded translator, not a local hook binding.
        if match.start() == 0 or text[match.start() - 1] != ".":
            for position, declared_namespace in declarations.get(alias, []):
                if position > match.start():
                    break
                namespace = declared_namespace
        # Include literals in a conditional first argument, but stop before
        # options or later arguments. Quoted strings and nested expressions
        # cannot end the outer argument at an internal comma or parenthesis.
        depth = 0
        end = len(text)
        for token in argument_tokens.finditer(text, match.end()):
            value = token.group()
            if value in {",", ")"} and depth == 0:
                end = token.start()
                break
            if value in {"(", "[", "{"}:
                depth += 1
            elif value in {")", "]", "}"}:
                depth -= 1
        for literal_pattern in (KEY_LITERAL, DYNAMIC_KEY_LITERAL):
            for literal in literal_pattern.finditer(text, match.end(), end):
                calls[literal.start()] = namespace
        # A wrapper can forward a parameter whose allowed keys are a literal
        # union. Keep that contract only when the parameter reaches a translator.
        argument = text[match.end() : end].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", argument):
            union_pattern = re.compile(
                rf"\b{re.escape(argument)}\s*:\s*"
                r"((?:\s*\|?\s*['\"][A-Za-z0-9_.-]+['\"])+)"
            )
            preceding_unions = list(union_pattern.finditer(text, 0, match.start()))
            for union in preceding_unions[-1:]:
                for literal in KEY_LITERAL.finditer(text, union.start(1), union.end(1)):
                    calls[literal.start()] = namespace
    return calls


def collect_literal_keys(
    text: str,
    defined_keys: set[str],
    relative_calls: dict[int, str] | None = None,
) -> set[str]:
    """Recognize key constants, forwarded relative keys, and dynamic families.

    A template preserves only the defined keys matching its fixed segments.
    Values for interpolated enums can come from API data, so do not guess their
    population. Relative literals must be translator arguments; unrelated
    dotted strings and bare words never preserve an entire namespace.
    """
    used: set[str] = set()
    relative_keys: dict[str, set[str]] = {}
    for key in defined_keys:
        parts = key.split(".")
        for index in range(1, len(parts) - 1):
            relative_keys.setdefault(".".join(parts[index:]), set()).add(key)

    for match in KEY_LITERAL.finditer(text):
        literal = match.group(2)
        if TRANSLATION_KEY_LITERAL.fullmatch(literal):
            used.add(literal)
            continue
        if (
            "." in literal
            and relative_calls is not None
            and match.start() in relative_calls
        ):
            namespace = relative_calls[match.start()]
            if namespace:
                used.add(f"{namespace}.{literal}")
            elif literal in relative_keys:
                used.update(relative_keys[literal])
    for match in DYNAMIC_KEY_LITERAL.finditer(text):
        literal = match.group(2)
        is_python_template = match.start() > 0 and text[match.start() - 1] in {"f", "F"}
        if "${" in literal:
            segments = re.split(r"\$\{[^}]*\}", literal)
        elif is_python_template and "{" in literal:
            segments = re.split(r"\{[^}]*\}", literal)
        else:
            continue
        if len(segments) < 2 or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_.-]*\.", segments[0]
        ):
            continue
        is_full_key = segments[0].startswith(
            ("common.", "component.", "module.", "server.")
        )
        if not is_full_key:
            if relative_calls is None or match.start() not in relative_calls:
                continue
            namespace = relative_calls[match.start()]
            if namespace:
                segments[0] = f"{namespace}.{segments[0]}"
                is_full_key = True
        pattern = re.compile("^" + ".*".join(re.escape(s) for s in segments) + "$")
        used.update(key for key in defined_keys if pattern.fullmatch(key))
        if not is_full_key:
            for relative, keys in relative_keys.items():
                if pattern.fullmatch(relative):
                    used.update(keys)
    return used


def collect_frontend_namespaced_keys(text: str) -> set[str]:
    """Collect frontend namespaced keys."""
    used: set[str] = set()
    alias_declarations: dict[str, list[tuple[int, str]]] = {}

    for match in USE_TRANSLATION_ALIAS_PATTERN.finditer(text):
        alias = match.group(1) or "t"
        namespace = match.group(2) or match.group(3)
        if namespace:
            alias_declarations.setdefault(alias, []).append((match.start(), namespace))

    for alias, declarations in alias_declarations.items():
        call_pattern = re.compile(
            rf"\b{re.escape(alias)}\(\s*['\"]([A-Za-z0-9_.-]+)['\"]"
        )
        for match in call_pattern.finditer(text):
            key = match.group(1)
            namespace = None
            for declaration_pos, declaration_namespace in declarations:
                if declaration_pos > match.start():
                    break
                namespace = declaration_namespace
            if not namespace:
                continue
            if key.startswith(("common.", "component.", "module.", "server.")):
                used.add(key)
            else:
                used.add(f"{namespace}.{key}")

    return used


def collect_frontend_trans_keys(text: str) -> set[str]:
    """Collect frontend trans keys."""
    used: set[str] = set()
    direct_key_pattern = re.compile(
        r"i18nKey\s*=\s*['\"]([A-Za-z0-9_.-]+)['\"]",
        re.DOTALL,
    )
    expression_key_pattern = re.compile(r"i18nKey\s*=\s*\{([^}]+)\}", re.DOTALL)
    namespace_pattern = re.compile(r"ns\s*=\s*['\"]([A-Za-z0-9_.-]+)['\"]")

    for match in direct_key_pattern.finditer(text):
        used.add(match.group(1))

    for match in expression_key_pattern.finditer(text):
        expr = match.group(1)
        trans_start = text.rfind("<Trans", 0, match.start())
        trans_segment = text[trans_start : match.start()] if trans_start >= 0 else ""
        namespace_match = namespace_pattern.search(trans_segment)
        namespace = namespace_match.group(1) if namespace_match else None

        for literal in re.findall(r"['\"]([A-Za-z0-9_.-]+)['\"]", expr):
            if literal.startswith(("common.", "component.", "module.", "server.")):
                used.add(literal)
            elif namespace:
                used.add(f"{namespace}.{literal}")

    return used


def iter_locale_dirs() -> Iterable[Path]:
    """Yield locale dirs."""
    if not I18N_DIR.exists():
        message = f"Translation directory not found: {I18N_DIR}"
        raise RuntimeError(message)
    for entry in sorted(I18N_DIR.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            yield entry


def flatten_translation(data: object, namespace: str) -> dict[str, str]:
    """Flatten translation."""
    if isinstance(data, dict):
        items: dict[str, str] = {}
        flat_section = data.get("__flat__")
        if isinstance(flat_section, dict):
            for key, value in flat_section.items():
                if not isinstance(value, str):
                    message = f"Translation value for '{key}' must be a string"
                    raise TypeError(message)
                composite_key = f"{namespace}.{key}" if namespace else key
                items[composite_key] = value
        for key, value in data.items():
            if key in {"__flat__", "__namespace__"}:
                continue
            next_namespace = f"{namespace}.{key}" if namespace else key
            items.update(flatten_translation(value, next_namespace))
        return items
    if not isinstance(data, str):
        message = f"Translation value for '{namespace}' must be a string"
        raise TypeError(message)
    return {namespace: data}


def collect_defined_keys() -> set[str]:
    """Collect defined keys."""
    locale_dirs = list(iter_locale_dirs())
    if not locale_dirs:
        return set()
    reference_locale = locale_dirs[0]
    defined: set[str] = set()
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


def load_metadata_namespaces() -> set[str]:
    """Load metadata namespaces."""
    namespaces: set[str] = set()
    meta = I18N_DIR / "locales.json"
    if not meta.exists():
        return namespaces
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        for ns in data.get("namespaces", []) or []:
            if isinstance(ns, str) and ns:
                namespaces.add(ns)
    except (OSError, ValueError):
        pass
    return namespaces


def collect_backend_keys() -> set[str]:
    """Collect backend keys."""
    patterns = BACKEND_PATTERNS
    used: set[str] = set()
    defined_keys = translation_aliases(collect_defined_keys())
    error_codes_path = BACKEND_DIR / "error_codes.json"
    if error_codes_path.is_file():
        error_codes = json.loads(error_codes_path.read_text(encoding="utf-8"))
        registered_keys = {
            key for key, code in error_codes.items() if isinstance(code, int)
        }
        # The runtime error registry is a compatibility contract even when a
        # particular code has no current literal raise site. Preserve existing
        # messages without treating legacy untranslated entries as new calls.
        used.update(translation_aliases(registered_keys) & defined_keys)
    for file_path in BACKEND_DIR.rglob("*.py"):
        if any(
            part in {"tests", ".venv", "venv"}
            for part in file_path.relative_to(BACKEND_DIR).parts
        ):
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        used.update(collect_literal_keys(text, defined_keys))
        for pattern in patterns:
            for match in pattern.findall(text):
                if "." not in match:
                    continue
                # Only consider backend namespaces we intentionally allow in Python.
                if match.startswith(("server.", "module.")):
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
                    elif match.startswith("module.backend."):
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


def collect_frontend_keys() -> set[str]:
    """Collect frontend keys."""
    if not WEB_DIR.is_dir():
        message = f"Web frontend source directory not found: {WEB_DIR}"
        raise RuntimeError(message)

    patterns = FRONTEND_PATTERNS
    used: set[str] = set()
    defined_keys = translation_aliases(collect_defined_keys())
    extensions = (".ts", ".tsx", ".js", ".jsx")
    for file_path in WEB_DIR.rglob("*"):
        if file_path.suffix not in extensions:
            continue
        if (
            ".test." in file_path.name
            or ".spec." in file_path.name
            or ".test-support." in file_path.name
            or file_path.name.endswith(".d.ts")
            or "__tests__" in file_path.parts
        ):
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            for match in pattern.findall(text):
                used.add(match)
        used.update(collect_frontend_namespaced_keys(text))
        used.update(collect_frontend_trans_keys(text))
        used.update(
            collect_literal_keys(
                text, defined_keys, collect_frontend_relative_calls(text)
            )
        )
    return used


def parse_args() -> argparse.Namespace:
    """Parse arguments for the translation-usage check."""
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


def load_allowlist(path: Path | None) -> set[str]:
    """Load allowlist."""
    if not path:
        return set()

    # Be resilient if legacy CI passes an allowlist path that no longer exists.
    # Treat missing file as empty allowlist instead of failing hard.
    if not path.exists():
        with contextlib.suppress(Exception):
            print(f"Allowlist file not found, treating as empty: {path}")
        return set()

    allowed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        allowed.add(stripped)
    return allowed


def main() -> int:
    """Compare defined translation keys with backend and frontend usage."""
    args = parse_args()
    defined_primary = collect_defined_keys()
    # Aliases for missing-key comparison only
    aliases: set[str] = set()
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
    used_keys = translation_aliases(backend_used | frontend_used)
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
    missing_allow_expanded: set[str] = set(missing_allow)
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
    elif allowed_missing:
        print("No new missing keys; allowed baseline present.")
    else:
        print("No missing translation keys detected.")

    if unused_keys:
        print("\nUnused translation keys detected (consider cleanup):")
        for key in unused_keys:
            print(f" - {key}")
    elif allowed_unused:
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
