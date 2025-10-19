from collections import defaultdict
import importlib.util
import json
import os
from pathlib import Path
import threading
from typing import Dict, Iterable

from flask import Flask

TRANSLATIONS_DEFAULT_NAME = "i18n"

_thread_local = threading.local()
_translations: Dict[str, Dict[str, str]] = defaultdict(dict)


def _shared_json_root() -> Path:
    return Path(__file__).resolve().parents[3] / "i18n"


def _flatten_dict(data, prefix: str = ""):
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
        for file_path in lang_dir.glob("*.json"):
            namespace = file_path.stem
            try:
                content = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - IO errors are logged
                app.logger.error(
                    "Failed to load translation file %s: %s", file_path, exc
                )
                continue

            for key, value in _flatten_dict(content, namespace).items():
                _store_translation(lang, key, value)


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

    _load_json_translations(app, _shared_json_root())
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
