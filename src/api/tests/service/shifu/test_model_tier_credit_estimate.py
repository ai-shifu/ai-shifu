"""Course estimates must price an effective selection, never an empty model."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.api.llm import model_selection
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu.admin_operations import courses_credit_estimate as estimates


@pytest.mark.parametrize("model", ["", " \t", None])
def test_estimate_rejects_missing_course_selection_before_pricing(
    app: object, monkeypatch: pytest.MonkeyPatch, model: str | None
) -> None:
    monkeypatch.setattr(model_selection, "get_config", lambda *_args: "")
    pricing = Mock()
    monkeypatch.setattr(estimates, "_sum_llm_cost", pricing)
    with app.app_context(), pytest.raises(AppError) as captured:
        estimates.build_operator_course_estimated_credit_cost(
            app,
            course=SimpleNamespace(llm=model),
            outline_items=[],
            visible_leaf_outline_bids=[],
        )
    assert captured.value.code == ERROR_CODE["server.llm.modelSelectionNotConfigured"]
    pricing.assert_not_called()


@pytest.mark.parametrize("tier", [None, "fast"])
def test_estimate_prices_legacy_or_resolved_tier_model(
    app: object, monkeypatch: pytest.MonkeyPatch, tier: str | None
) -> None:
    """Capture the pricing boundary without mocking selection resolution itself."""
    monkeypatch.setattr(model_selection, "resolve_model_slot", lambda _tier: "mapped-1")
    expected = "mapped-1"
    pricing = Mock(side_effect=RuntimeError("pricing reached"))
    monkeypatch.setattr(estimates, "_sum_llm_cost", pricing)
    with app.app_context(), pytest.raises(RuntimeError, match="pricing reached"):
        estimates.build_operator_course_estimated_credit_cost(
            app,
            course=SimpleNamespace(llm=tier or "legacy-model"),
            outline_items=[],
            visible_leaf_outline_bids=[],
        )
    assert pricing.call_args.kwargs["model"] == expected
