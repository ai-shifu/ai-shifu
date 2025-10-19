from collections import defaultdict
import importlib.util
import json
import os
from pathlib import Path
import threading
from typing import Dict, Iterable, List

from flask import Flask

TRANSLATIONS_DEFAULT_NAME = "i18n"

_thread_local = threading.local()
_translations: Dict[str, Dict[str, str]] = defaultdict(dict)


def _shared_json_root() -> Path:
    env_override = os.getenv("SHARED_I18N_ROOT")
    if env_override:
        env_path = Path(env_override).resolve()
        if env_path.exists():
            return env_path

    candidates = [
        Path(__file__).resolve().parents[3] / "i18n",
        Path(__file__).resolve().parents[2] / "i18n",
        Path(__file__).resolve().parents[1] / "i18n",
        Path(__file__).resolve().parent / "json",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Default fallback; validation will raise a clearer error later
    return Path(__file__).resolve().parents[2] / "i18n"


def _flatten_dict(data, prefix: str = ""):
    if not isinstance(data, dict):
        key = prefix if prefix else ""
        return {key: data} if key else {}

    flattened = {}
    for key, value in data.items():
        str_key = str(key)
        composite_key = f"{prefix}.{str_key}" if prefix else str_key
        if isinstance(value, dict):
            flattened.update(_flatten_dict(value, composite_key))
        else:
            flattened[composite_key] = value
    return flattened


def _store_translation(lang: str, key: str, value):
    if value is None:
        return
    _translations[lang][key] = value
    _translations[lang][key.upper()] = value

    # Temporary bidirectional aliasing between legacy and new backend namespaces
    # to support gradual migration:
    # - module.backend.<domain>.<key>  <->  server.<domain>.<key>
    if key.startswith("module.backend."):
        alias = "server." + key[len("module.backend.") :]
        _translations[lang][alias] = value
        _translations[lang][alias.upper()] = value
    elif key.startswith("server."):
        alias = "module.backend." + key[len("server.") :]
        _translations[lang][alias] = value
        _translations[lang][alias.upper()] = value
    # Domain rename transitional aliases
    # course -> shifu
    if key.startswith("module.backend.course."):
        tail = key[len("module.backend.course.") :]
        alias = f"server.shifu.{tail}"
        _translations[lang][alias] = value
        _translations[lang][alias.upper()] = value
    elif key.startswith("server.shifu."):
        tail = key[len("server.shifu.") :]
        alias = f"module.backend.course.{tail}"
        _translations[lang][alias] = value
        _translations[lang][alias.upper()] = value
    # lesson -> outline / outlineItem
    if key.startswith("module.backend.lesson."):
        tail = key[len("module.backend.lesson.") :]
        alias1 = f"server.outline.{tail}"
        alias2 = f"server.outlineItem.{tail}"
        _translations[lang][alias1] = value
        _translations[lang][alias1.upper()] = value
        _translations[lang][alias2] = value
        _translations[lang][alias2.upper()] = value
    elif key.startswith("server.outline.") or key.startswith("server.outlineItem."):
        prefix = (
            "server.outline."
            if key.startswith("server.outline.")
            else "server.outlineItem."
        )
        tail = key[len(prefix) :]
        alias = f"module.backend.lesson.{tail}"
        _translations[lang][alias] = value
        _translations[lang][alias.upper()] = value


def _load_json_translations(app: Flask, root: Path):
    if not root.exists():
        app.logger.debug("i18n JSON directory not found: %s", root)
        return

    metadata_path = root / "locales.json"
    language_codes: Iterable[str] = []

    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            language_codes = metadata.get("locales", {}).keys()
        except Exception as exc:  # pragma: no cover - defensive log
            app.logger.error(
                "Failed to parse locales metadata at %s: %s", metadata_path, exc
            )

    if not language_codes:
        language_codes = (
            entry.name
            for entry in root.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )

    for lang in language_codes:
        lang_dir = root / lang
        if not lang_dir.is_dir():
            app.logger.warning(
                "Translation directory missing for language %s: %s", lang, lang_dir
            )
            continue

        app.logger.info("load_json_translations lang: %s", lang)
        for file_path in lang_dir.rglob("*.json"):
            if file_path.name.startswith("."):
                continue

            try:
                namespace = str(
                    file_path.relative_to(lang_dir).with_suffix("")
                ).replace(os.sep, ".")
            except ValueError:
                namespace = file_path.stem
            try:
                content = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - IO errors are logged
                app.logger.error(
                    "Failed to load translation file %s: %s", file_path, exc
                )
                continue

            flat_entries = {}
            if isinstance(content, dict) and "__flat__" in content:
                flat_section = content.get("__flat__", {})
                namespace_override = content.get("__namespace__")
                residual = {
                    key: value
                    for key, value in content.items()
                    if key not in {"__flat__", "__namespace__"}
                }
                base_namespace = (
                    namespace_override
                    if isinstance(namespace_override, str) and namespace_override
                    else namespace
                )
                # 1) store flat-section with namespace prefix
                if isinstance(flat_section, dict):
                    for k, v in flat_section.items():
                        qualified = f"{base_namespace}.{k}" if base_namespace else k
                        _store_translation(lang, qualified, v)
                # 2) store nested residuals with namespace prefix
                for key, value in _flatten_dict(residual, base_namespace).items():
                    _store_translation(lang, key, value)
            else:
                flat_entries.update(_flatten_dict(content, namespace))
                for key, value in flat_entries.items():
                    _store_translation(lang, key, value)


def _validate_json_translations(app: Flask, root: Path):
    if not root.exists():
        raise FileNotFoundError(
            f"Missing shared i18n directory at '{root}'. Run the migration checklist to generate JSON translations."
        )

    problems: List[str] = []

    metadata_path = root / "locales.json"
    metadata_declared_locales: set[str] = set()
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata_declared_locales = set(metadata.get("locales", {}).keys())
            default_locale = metadata.get("default")
            if default_locale and default_locale not in metadata_declared_locales:
                problems.append(
                    f"Default locale '{default_locale}' listed in {metadata_path} is missing from locales map."
                )
        except Exception as exc:
            problems.append(f"Invalid locales metadata JSON: {metadata_path} ({exc})")
    else:
        problems.append(f"Missing locales metadata file: {metadata_path}")

    locale_dirs = [
        entry
        for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    ]

    if not locale_dirs:
        problems.append(f"No locale directories found under '{root}'.")

    locale_dir_names = {locale_dir.name for locale_dir in locale_dirs}

    if metadata_declared_locales:
        missing_locale_dirs = metadata_declared_locales - locale_dir_names
        if missing_locale_dirs:
            problems.append(
                "Locales declared in metadata but missing directories: "
                + ", ".join(sorted(missing_locale_dirs))
            )

        missing_metadata_entries = locale_dir_names - metadata_declared_locales
        if missing_metadata_entries:
            problems.append(
                "Locale directories missing from metadata locales map: "
                + ", ".join(sorted(missing_metadata_entries))
            )

    for locale_dir in locale_dirs:
        json_files = list(locale_dir.rglob("*.json"))
        if not json_files:
            problems.append(
                f"Locale '{locale_dir.name}' does not contain any JSON translation files."
            )
            continue

        for file_path in json_files:
            try:
                json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as exc:
                problems.append(f"Malformed JSON in {file_path}: {exc}")

    if problems:
        details = "\n - ".join(["Detected translation issues:"] + problems)
        raise RuntimeError(details)


def _load_python_translations(app: Flask, translations_dir: Path):
    if not translations_dir.exists():
        return

    for lang in os.listdir(translations_dir):
        lang_dir = os.path.join(translations_dir, lang)
        if os.path.isdir(lang_dir) and lang_dir != "__pycache__" and lang_dir[0] != ".":
            app.logger.info("load_python_translations lang: %s", lang)
            for module_name in os.listdir(lang_dir):
                module_path = os.path.join(lang_dir, module_name)
                if os.path.isdir(module_path):
                    for file_name in os.listdir(module_path):
                        if file_name.endswith(".py"):
                            file_path = os.path.join(module_path, file_name)
                            spec = importlib.util.spec_from_file_location(
                                module_name, file_path
                            )
                            module = importlib.util.module_from_spec(spec)
                            if spec.loader is None:
                                continue
                            spec.loader.exec_module(module)
                            for var_name in dir(module):
                                if not var_name.startswith("__"):
                                    key = module_name.upper() + "." + var_name.upper()
                                    _store_translation(
                                        lang, key, getattr(module, var_name)
                                    )


def load_translations(app: Flask, translations_dir=None):
    if translations_dir:
        base_path = Path(translations_dir)
        _load_json_translations(app, base_path)
        _load_python_translations(app, base_path)
        return

    _translations.clear()

    shared_root = _shared_json_root()
    try:
        _validate_json_translations(app, shared_root)
    except Exception as exc:
        app.logger.error("i18n validation failed: %s", exc)
        raise

    _load_json_translations(app, shared_root)
    _load_python_translations(app, Path(__file__).resolve().parent)


def _(text: str):
    language = getattr(_thread_local, "language", "en-US")
    translations = _translations.get(language) or _translations.get("en-US", {})
    return translations.get(text) or translations.get(text.upper(), text)


def get_current_language():
    return getattr(_thread_local, "language", "en-US")


def set_language(language):
    _thread_local.language = language


def get_i18n_list(app: Flask):
    return list(_translations.keys())


__all__ = ["_", "set_language", "get_i18n_list", "load_translations"]
