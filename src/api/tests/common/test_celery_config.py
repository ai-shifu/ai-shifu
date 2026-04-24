from __future__ import annotations

from flaskr.common.config import ENV_VARS, EnhancedConfig


def test_env_registry_includes_celery_runtime_variables() -> None:
    assert "CELERY_BROKER_URL" in ENV_VARS
    assert ENV_VARS["CELERY_BROKER_URL"].group == "celery"
    assert ENV_VARS["CELERY_RESULT_BACKEND"].group == "celery"
    assert ENV_VARS["CELERY_TASK_ALWAYS_EAGER"].type is bool
    assert ENV_VARS["BILLING_RENEWAL_CRON"].group == "celery"
    assert ENV_VARS["BILLING_BUCKET_EXPIRE_CRON"].group == "celery"
    assert ENV_VARS["BILLING_LOW_BALANCE_CRON"].group == "celery"


def test_env_example_exports_celery_variables() -> None:
    output = EnhancedConfig(ENV_VARS).export_env_example()

    assert 'CELERY_BROKER_URL="redis://localhost:6379/0"' in output
    assert 'CELERY_RESULT_BACKEND="redis://localhost:6379/1"' in output
    assert 'CELERY_TASK_ALWAYS_EAGER="False"' in output
    assert 'BILLING_RENEWAL_CRON="* * * * *"' in output
    assert 'BILLING_BUCKET_EXPIRE_CRON="* * * * *"' in output
    assert 'BILLING_LOW_BALANCE_CRON="0 * * * *"' in output
