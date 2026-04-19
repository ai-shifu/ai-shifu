import os
from pathlib import Path
import subprocess
import sys
import textwrap
import uuid

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


API_ROOT = Path(__file__).resolve().parents[2]
SMOKE_FLAG = "RUN_MYSQL_MIGRATION_SMOKE"
MYSQL_URI_ENV = "TEST_SQLALCHEMY_DATABASE_URI"


def _get_expected_head() -> str:
    config = Config(str(API_ROOT / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def _get_base_mysql_uri() -> str:
    if os.getenv(SMOKE_FLAG) != "1":
        pytest.skip(f"Set {SMOKE_FLAG}=1 to run the fresh-MySQL migration smoke test.")

    base_uri = os.getenv(MYSQL_URI_ENV)
    if not base_uri:
        pytest.skip(f"Set {MYSQL_URI_ENV} to a MySQL admin DSN to run this smoke test.")

    url = make_url(base_uri)
    if not url.drivername.startswith("mysql"):
        pytest.skip(f"{MYSQL_URI_ENV} must use a MySQL driver.")

    return base_uri


def _create_temp_database(base_uri: str) -> tuple[str, str]:
    base_url = make_url(base_uri)
    admin_url = base_url.set(database="mysql")
    database_name = f"ai_shifu_migration_smoke_{uuid.uuid4().hex[:12]}"
    temp_url = base_url.set(database=database_name)

    admin_engine = create_engine(
        admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
    admin_engine.dispose()

    return temp_url.render_as_string(hide_password=False), database_name


def _drop_temp_database(base_uri: str, database_name: str) -> None:
    admin_url = make_url(base_uri).set(database="mysql")
    admin_engine = create_engine(
        admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
    admin_engine.dispose()


def _migration_subprocess_script() -> str:
    return textwrap.dedent(
        """
        import os
        import sys
        import types

        os.environ["SKIP_LOAD_DOTENV"] = "1"
        os.environ["SKIP_APP_AUTOCREATE"] = "1"
        os.environ["SECRET_KEY"] = "mysql-migration-smoke"
        os.environ["DEFAULT_LLM_MODEL"] = "gpt-test"
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SAAS_DB_URI"] = os.environ["SQLALCHEMY_DATABASE_URI"]
        os.environ["ADMIN_DB_URI"] = os.environ["SQLALCHEMY_DATABASE_URI"]
        os.environ["REDIS_HOST"] = ""
        os.environ["REDIS_PORT"] = ""

        litellm = types.ModuleType("litellm")
        litellm.completion = lambda *args, **kwargs: None
        litellm.get_max_tokens = lambda _model: 4096
        sys.modules["litellm"] = litellm

        langfuse = types.ModuleType("langfuse")

        class _Langfuse:
            def __init__(self, *args, **kwargs):
                pass

        langfuse.Langfuse = _Langfuse
        sys.modules["langfuse"] = langfuse

        client_mod = types.ModuleType("langfuse.client")

        class StatefulSpanClient:
            pass

        class StatefulTraceClient:
            pass

        client_mod.StatefulSpanClient = StatefulSpanClient
        client_mod.StatefulTraceClient = StatefulTraceClient
        sys.modules["langfuse.client"] = client_mod

        model_mod = types.ModuleType("langfuse.model")

        class ModelUsage:
            pass

        model_mod.ModelUsage = ModelUsage
        sys.modules["langfuse.model"] = model_mod

        from app import create_app
        from flask_migrate import upgrade

        app = create_app()
        with app.app_context():
            upgrade("migrations")
        """
    )


def test_fresh_mysql_upgrade_reaches_head():
    base_uri = _get_base_mysql_uri()
    temp_uri, database_name = _create_temp_database(base_uri)
    expected_head = _get_expected_head()

    env = os.environ.copy()
    env["SQLALCHEMY_DATABASE_URI"] = temp_uri

    try:
        result = subprocess.run(
            [sys.executable, "-c", _migration_subprocess_script()],
            cwd=API_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, (
            "Fresh MySQL migration smoke test failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

        engine = create_engine(temp_uri)
        with engine.connect() as conn:
            current_head = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        engine.dispose()

        assert current_head == expected_head
        assert {
            "sys_configs",
            "user_users",
            "var_variables",
            "learn_lesson_feedbacks",
        }.issubset(tables)
    finally:
        _drop_temp_database(base_uri, database_name)
