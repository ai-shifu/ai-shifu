from __future__ import annotations

from pathlib import Path

from flaskr.service.billing.consts import BILL_SYS_CONFIG_SEEDS

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_sys_config_bootstrap_moves_out_of_alembic() -> None:
    migration_source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")
    cli_source = (_API_ROOT / "flaskr/service/billing/cli.py").read_text(
        encoding="utf-8"
    )

    assert "op.bulk_insert(" not in migration_source
    assert "seed-bootstrap-data" in cli_source
    assert "BILL_SYS_CONFIG_SEEDS" in cli_source
    assert "seed_billing_bootstrap_data" in cli_source
    assert len(BILL_SYS_CONFIG_SEEDS) == 4
