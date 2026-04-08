from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_funcs_only_depend_on_shared_payment_provider_adapter() -> None:
    source = (_API_ROOT / "flaskr/service/billing/funcs.py").read_text(encoding="utf-8")

    assert "from flaskr.service.order.payment_providers import (" in source
    assert "PaymentRequest," in source
    assert "get_payment_provider," in source
    assert "provider = get_payment_provider(payment_provider)" in source
    assert "result = provider.create_subscription(" in source
    assert "result = provider.create_payment(" in source
    assert "provider.verify_webhook(" in source
    assert "provider.sync_reference(" in source
    assert "import stripe" not in source
    assert "import pingxx" not in source


def test_shared_payment_provider_base_exposes_billing_required_hooks() -> None:
    source = (_API_ROOT / "flaskr/service/order/payment_providers/base.py").read_text(
        encoding="utf-8"
    )

    assert "class PaymentProvider(ABC):" in source
    assert "def create_payment(" in source
    assert "def create_subscription(" in source
    assert "def cancel_subscription(" in source
    assert "def resume_subscription(" in source
    assert "def verify_webhook(" in source
    assert "def sync_reference(" in source
