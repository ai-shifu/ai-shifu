"""Guard the staged removal of deprecated Pydantic Field metadata."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from flasgger import Swagger
from flask import Flask
from flaskr.common.swagger import swagger_config
from flaskr.service.shifu.admin_dtos_users import (
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationUserPackageGrantRequestDTO,
)
from pydantic import ValidationError

API_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = API_ROOT / "flaskr" / "service"

# These are the second migration batch. Exact counts make the temporary
# allowance a ratchet: existing debt is visible and new uses still fail.
TEMPORARY_REQUIRED_ALLOWLIST = {
    Path("shifu/dtos.py"): 58,
    Path("learn/learn_dtos.py"): 52,
    Path("user/dtos.py"): 6,
}

ADMIN_DTO_MODULES = (
    "flaskr.service.dashboard.dtos",
    "flaskr.service.order.admin_dtos",
    "flaskr.service.promo.admin_dtos",
    "flaskr.service.shifu.admin_dtos_courses",
    "flaskr.service.shifu.admin_dtos_users",
)


def _pydantic_field_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    direct_names: set[str] = set()
    module_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "pydantic":
            for imported in node.names:
                if imported.name == "Field":
                    direct_names.add(imported.asname or imported.name)
        elif isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name == "pydantic":
                    module_names.add(imported.asname or imported.name)
    return direct_names, module_names


def _is_pydantic_field_call(
    node: ast.Call, direct_names: set[str], module_names: set[str]
) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id in direct_names
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "Field"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in module_names
    )


def _deprecated_required_counts() -> Counter[Path]:
    counts: Counter[Path] = Counter()
    for source_path in SERVICE_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), source_path)
        direct_names, module_names = _pydantic_field_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_pydantic_field_call(
                node, direct_names, module_names
            ):
                continue
            if any(keyword.arg == "required" for keyword in node.keywords):
                counts[source_path.relative_to(SERVICE_ROOT)] += 1
    return counts


def test_pydantic_field_required_debt_matches_second_batch_allowlist() -> None:
    """Keep cleaned modules clean and prevent growth before batch two lands."""
    assert _deprecated_required_counts() == Counter(TEMPORARY_REQUIRED_ALLOWLIST)


def test_admin_dto_imports_emit_no_field_required_deprecation() -> None:
    """Import every cleaned module afresh without hiding the target warning."""
    import_code = f"""
import importlib
import warnings
from pydantic.warnings import PydanticDeprecatedSince20

warnings.filterwarnings(
    "error",
    message=r"Using extra keyword arguments on `Field`.*required",
    category=PydanticDeprecatedSince20,
)
for module_name in {ADMIN_DTO_MODULES!r}:
    importlib.import_module(module_name)
"""
    subprocess.run(
        [sys.executable, "-c", import_code],
        cwd=API_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_operator_grant_request_required_fields_and_defaults_are_preserved() -> None:
    """Keep request validation stable without executing a real grant."""
    with pytest.raises(ValidationError):
        AdminOperationUserCreditGrantRequestDTO.model_validate(
            {
                "amount": "100",
                "grant_source": "reward",
                "validity_preset": "30_days",
            }
        )

    credit_request = AdminOperationUserCreditGrantRequestDTO.model_validate(
        {
            "request_id": "grant-request-1",
            "amount": "100",
            "grant_source": "reward",
            "validity_preset": "30_days",
        }
    )
    assert credit_request.__json__() == {
        "request_id": "grant-request-1",
        "amount": "100",
        "grant_type": "manual_credit",
        "grant_source": "reward",
        "validity_preset": "30_days",
        "display_name": "",
        "note": "",
    }

    with pytest.raises(ValidationError):
        AdminOperationUserPackageGrantRequestDTO.model_validate(
            {"request_id": "package-request-1"}
        )

    package_request = AdminOperationUserPackageGrantRequestDTO.model_validate(
        {"request_id": "package-request-1", "product_bid": "plan-1"}
    )
    assert package_request.__json__() == {
        "request_id": "package-request-1",
        "product_bid": "plan-1",
        "note": "",
    }


def test_actual_openapi_keeps_standard_required_arrays() -> None:
    """Exercise Flasgger's real JSON endpoint, not only Pydantic schemas."""
    app = Flask(__name__)
    Swagger(app, config=swagger_config, merge=True)

    response = app.test_client().get("/apispec_1.json")

    assert response.status_code == 200
    schemas = response.get_json()["components"]["schemas"]
    assert schemas["AdminOperationUserCreditGrantRequestDTO"]["required"] == [
        "request_id",
        "amount",
        "grant_type",
        "grant_source",
        "validity_preset",
        "display_name",
        "note",
    ]
    assert schemas["AdminOperationUserPackageGrantRequestDTO"]["required"] == [
        "request_id",
        "product_bid",
        "note",
    ]
