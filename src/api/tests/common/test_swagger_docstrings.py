"""Validate every source-defined Flasgger docstring as a runtime contract."""

import ast
from pathlib import Path

from flasgger.utils import parse_docstring
from flaskr.common.swagger import sanitize_swagger_docstring
from yaml import YAMLError

API_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SWAGGER_DOCSTRING_COUNT = 114
KNOWN_UNPARSEABLE_SWAGGER_DOCSTRINGS = {
    ("flaskr/service/learn/routes.py", "preview_outline_block_api"),
    ("flaskr/service/learn/routes.py", "run_outline_item_api"),
    ("flaskr/service/learn/routes.py", "synthesize_generated_block_audio_api"),
}


def _swagger_docstrings():
    for path in (API_ROOT / "flaskr").rglob("*.py"):
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = ast.get_docstring(node, clean=False)
            if docstring and any(
                line.strip() == "---" for line in docstring.splitlines()
            ):
                yield path.relative_to(API_ROOT), node.name, docstring


def test_swagger_sanitizer_omits_framing_newlines() -> None:
    assert sanitize_swagger_docstring("\nReset the chapter order.\n\n") == (
        "Reset the chapter order."
    )


def test_all_swagger_docstrings_keep_valid_yaml_after_summary() -> None:
    discovered = []
    unparseable = set()
    for path, function_name, docstring in _swagger_docstrings():
        discovered.append((path, function_name))
        lines = docstring.splitlines()
        separator_index = next(
            index for index, line in enumerate(lines) if line.strip() == "---"
        )
        assert separator_index > 1, (path, function_name)
        assert lines[1].strip() == "", (path, function_name)

        def view():
            pass

        view.__doc__ = docstring
        try:
            summary, description, specification = parse_docstring(
                view,
                process_doc=sanitize_swagger_docstring,
            )
        except YAMLError:
            unparseable.add((str(path), function_name))
            continue
        assert summary == lines[0].strip(), (path, function_name)
        assert isinstance(description, str), (path, function_name)
        description_source = "\n".join(lines[1:separator_index])
        if not description_source.strip():
            assert description == "", (path, function_name)
        assert isinstance(specification, dict), (path, function_name)
        assert specification, (path, function_name)

    assert len(discovered) == EXPECTED_SWAGGER_DOCSTRING_COUNT
    assert unparseable == KNOWN_UNPARSEABLE_SWAGGER_DOCSTRINGS
