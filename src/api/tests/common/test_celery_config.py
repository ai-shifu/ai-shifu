from __future__ import annotations

from flaskr.common.config import ENV_VARS, EnhancedConfig


def test_env_registry_includes_celery_runtime_variables() -> None:
    assert "CELERY_BROKER_URL" in ENV_VARS
    assert ENV_VARS["CELERY_BROKER_URL"].group == "celery"
    assert ENV_VARS["CELERY_RESULT_BACKEND"].group == "celery"
    assert ENV_VARS["CELERY_TASK_ALWAYS_EAGER"].type is bool


def test_env_example_exports_celery_variables() -> None:
    output = EnhancedConfig(ENV_VARS).export_env_example()

    assert 'CELERY_BROKER_URL="redis://localhost:6379/0"' in output
    assert 'CELERY_RESULT_BACKEND="redis://localhost:6379/1"' in output
    assert 'CELERY_TASK_ALWAYS_EAGER="False"' in output
