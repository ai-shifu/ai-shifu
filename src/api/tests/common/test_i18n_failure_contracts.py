"""Validate translation startup failures and optional plugin loading boundaries."""

import json
import threading
from collections import defaultdict
from pathlib import Path

import pytest
from flask import Flask
from flaskr import i18n


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, "_translations", defaultdict(dict))
    monkeypatch.setattr(i18n, "_locale_labels", {})
    monkeypatch.setattr(i18n, "_thread_local", threading.local())


def _write(root: Path, name: str, payload: object) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({}, "Missing locales metadata file"),
        ({"locales.json": {"locales": {"en-US": {}}}}, "No locale directories"),
        (
            {
                "locales.json": {"default": "fr-FR", "locales": {"en-US": {}}},
                "en-US/app.json": {},
            },
            "Default locale 'fr-FR'",
        ),
        (
            {
                "locales.json": {"locales": {"en-US": {}, "fr-FR": {}}},
                "en-US/app.json": {},
            },
            "missing directories: fr-FR",
        ),
        (
            {
                "locales.json": {"locales": {"en-US": {}}},
                "en-US/app.json": {},
                "fr-FR/app.json": {},
            },
            "missing from metadata locales map: fr-FR",
        ),
        ({"locales.json": []}, "Invalid locales metadata JSON"),
    ],
)
def test_invalid_translation_tree_reports_actionable_cause(
    tmp_path: Path,
    files: dict,
    expected: str,
) -> None:
    for name, payload in files.items():
        _write(tmp_path, name, payload)
    with pytest.raises(RuntimeError, match=expected):
        i18n._validate_json_translations(tmp_path)


def test_empty_language_and_malformed_file_are_both_reported(tmp_path: Path) -> None:
    _write(tmp_path, "locales.json", {"locales": {"en-US": {}, "fr-FR": {}}})
    (tmp_path / "en-US").mkdir()
    (tmp_path / "fr-FR").mkdir()
    (tmp_path / "fr-FR/app.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError) as error:
        i18n._validate_json_translations(tmp_path)
    assert "does not contain any JSON" in str(error.value)
    assert "Malformed JSON" in str(error.value)


def test_missing_shared_directory_blocks_startup_but_optional_plugin_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "absent"
    i18n.load_translations(Flask(__name__), root)
    assert not i18n._translations
    monkeypatch.setattr(i18n, "_shared_json_root", lambda: root)
    with pytest.raises(FileNotFoundError, match="Missing shared i18n directory"):
        i18n.load_translations(Flask(__name__))


def test_plugin_json_namespace_flat_nested_and_scalar_values(tmp_path: Path) -> None:
    _write(tmp_path, "locales.json", {"locales": {"en-US": "English", "fr-FR": {}}})
    _write(
        tmp_path,
        "en-US/ui/buttons.json",
        {
            "__namespace__": "plugin",
            "__flat__": {"save": "Save", "omitted": None},
            "nested": {"cancel": "Cancel"},
        },
    )
    _write(tmp_path, "en-US/scalar.json", "Scalar label")
    _write(tmp_path, "en-US/invalid-flat.json", {"__flat__": [], "fallback": "Kept"})
    _write(tmp_path, "en-US/.private.json", {"secret": "ignored"})
    i18n.load_translations(Flask(__name__), tmp_path)
    assert i18n.translate_for_language("plugin.save", "en-US") == "Save"
    assert i18n.translate_for_language("PLUGIN.NESTED.CANCEL", "en-US") == "Cancel"
    assert i18n.translate_for_language("scalar", "en-US") == "Scalar label"
    assert i18n.translate_for_language("invalid-flat.fallback", "en-US") == "Kept"
    assert "plugin.omitted" not in i18n._translations["en-US"]
    assert all("secret" not in key for key in i18n._translations["en-US"])
    assert i18n.get_locale_labels() == {"en-US": "en-US", "fr-FR": "fr-FR"}
    labels = i18n.get_locale_labels()
    labels.clear()
    assert i18n.get_locale_labels()


def test_plugin_without_metadata_discovers_visible_locale_directories(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "en-US/app.json", {"greeting": "Hello"})
    _write(tmp_path, ".hidden/app.json", {"greeting": "Hidden"})
    i18n._load_json_translations(Flask(__name__), tmp_path)
    assert i18n.get_i18n_list() == ["en-US"]
    assert i18n.get_locale_labels() == {"en-US": "en-US"}


def test_legacy_plugin_python_translations_are_namespaced(tmp_path: Path) -> None:
    directory = tmp_path / "en-US" / "plugin"
    directory.mkdir(parents=True)
    (directory / "messages.py").write_text(
        'GREETING = "Hello from plugin"\n__private = "hidden"\n', encoding="utf-8"
    )
    (directory / "readme.txt").write_text("ignored", encoding="utf-8")
    i18n._load_python_translations(Flask(__name__), tmp_path)
    assert (
        i18n.translate_for_language("plugin.greeting", "en-US") == "Hello from plugin"
    )
    assert "PLUGIN.__PRIVATE" not in i18n._translations["en-US"]


def test_language_state_is_isolated_across_threads() -> None:
    observed = []
    i18n.set_language("fr-FR")

    def worker() -> None:
        observed.append(i18n.get_current_language())
        i18n.set_language("zh-CN")
        observed.append(i18n.get_current_language())
        i18n.clear_language()
        observed.append(i18n.get_current_language())

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert observed == ["en-US", "zh-CN", "en-US"]
    assert i18n.get_current_language() == "fr-FR"


def test_shared_root_falls_back_when_override_or_all_candidates_are_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(i18n, "get_config", lambda _key: str(tmp_path / "absent"))
    assert i18n._shared_json_root().is_dir()
    monkeypatch.setattr(i18n.Path, "exists", lambda _path: False)
    assert i18n._shared_json_root() == Path(i18n.__file__).resolve().parents[2] / "i18n"


def test_flattening_non_mapping_without_namespace_does_not_invent_a_key() -> None:
    assert i18n._flatten_dict(["unscoped"]) == {}
