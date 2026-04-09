from __future__ import annotations

import ast
from pathlib import Path


_ALLOWED_SERIALIZATION_METHODS = {
    "__json__",
    "to_dto_kwargs",
    "to_metadata_json",
    "to_payload",
    "to_provider_payload",
    "to_public_payload",
    "to_response_dict",
    "to_task_payload",
}


def test_billing_functions_do_not_return_raw_dict_annotations() -> None:
    billing_root = (
        Path(__file__).resolve().parents[3] / "flaskr" / "service" / "billing"
    )

    violations: list[str] = []
    for path in sorted(billing_root.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.returns is None:
                continue
            return_text = ast.unparse(node.returns)
            if not any(
                token in return_text for token in ("dict", "Mapping", "MutableMapping")
            ):
                continue
            if node.name in _ALLOWED_SERIALIZATION_METHODS:
                continue
            if path.name == "tasks.py" and node.name.endswith("_task"):
                continue
            violations.append(f"{path.name}:{node.lineno}:{node.name} -> {return_text}")

    assert not violations, "Unexpected raw dict return annotations:\n" + "\n".join(
        violations
    )


def test_billing_functions_do_not_return_raw_dict_literals() -> None:
    billing_root = (
        Path(__file__).resolve().parents[3] / "flaskr" / "service" / "billing"
    )

    violations: list[str] = []
    for path in sorted(billing_root.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in _ALLOWED_SERIALIZATION_METHODS:
                continue
            if path.name == "tasks.py" and node.name.endswith("_task"):
                continue

            dict_assigned_names: set[str] = set()
            for child in ast.walk(node):
                if not isinstance(child, ast.Assign):
                    continue
                if not isinstance(child.value, (ast.Dict, ast.DictComp)):
                    continue
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        dict_assigned_names.add(target.id)

            for child in ast.walk(node):
                if not isinstance(child, ast.Return) or child.value is None:
                    continue
                if isinstance(child.value, (ast.Dict, ast.DictComp)):
                    violations.append(
                        f"{path.name}:{child.lineno}:{node.name} -> raw dict literal"
                    )
                    continue
                if (
                    isinstance(child.value, ast.Name)
                    and child.value.id in dict_assigned_names
                ):
                    violations.append(
                        f"{path.name}:{child.lineno}:{node.name} -> dict variable '{child.value.id}'"
                    )

    assert not violations, "Unexpected raw dict return bodies:\n" + "\n".join(
        violations
    )
