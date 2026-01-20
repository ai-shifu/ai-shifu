# ruff: noqa: E402
import os
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

# Prevent accidental loading of user/global .env files during tests
os.environ.setdefault("SKIP_LOAD_DOTENV", "1")
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
os.environ.setdefault("SKIP_DB_MIGRATIONS_FOR_TESTS", "1")

from flaskr.common.config import ENV_VARS

# Clean environment for deterministic config tests.
_PRESERVE_ENV_KEYS = {
    "SKIP_LOAD_DOTENV",
    "SKIP_APP_AUTOCREATE",
    "SKIP_DB_MIGRATIONS_FOR_TESTS",
}
for _key in list(ENV_VARS.keys()):
    if _key in _PRESERVE_ENV_KEYS:
        continue
    os.environ.pop(_key, None)

# Force SQLite for tests unless explicitly overridden.
_test_db_uri = os.environ.get("TEST_SQLALCHEMY_DATABASE_URI")
_test_db_dir = None
if not _test_db_uri:
    _test_db_dir = Path(tempfile.mkdtemp(prefix="ai-shifu-test-"))
    _test_db_path = _test_db_dir / "test.db"
    _test_db_uri = f"sqlite:///{_test_db_path}"

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import BIGINT, LONGTEXT
from sqlalchemy.ext.compiler import compiles
from flaskr import dao
from flaskr.framework.plugin import plugin_manager as plugin_manager_module


class _TestPluginManager:
    def __init__(self):
        self.extension_functions = {}
        self.extensible_generic_functions = {}
        self.is_enabled = False

    def register_extension(self, target_func_name, func):
        self.extension_functions.setdefault(target_func_name, []).append(func)

    def execute_extensions(self, _func_name, result, *args, **kwargs):
        return result

    def register_extensible_generic(self, func_name, func):
        self.extensible_generic_functions.setdefault(func_name, []).append(func)

    def execute_extensible_generic(self, _func_name, *args, **kwargs):
        return None


plugin_manager_module.plugin_manager = _TestPluginManager()


@compiles(LONGTEXT, "sqlite")
def _compile_longtext_sqlite(_type, _compiler, **_kw):
    return "TEXT"


@compiles(BIGINT, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


if dao.db is None:
    dao.db = SQLAlchemy()

from tests.common.fixtures.fake_llm import (
    fake_chat_llm,
    fake_get_allowed_models,
    fake_get_current_models,
    fake_invoke_llm,
)
from tests.common.fixtures.fake_redis import FakeRedis


# Path: test/test_flaskr.py
# Compare this snippet from flaskr/plugin/test.py:
# from ..service.schedule import *
#
@pytest.fixture(scope="session")
def app():
    if os.getenv("SKIP_APP_FIXTURE"):
        yield None
        return
    original_env = os.environ.copy()
    os.environ["SQLALCHEMY_DATABASE_URI"] = _test_db_uri
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["UNIVERSAL_VERIFICATION_CODE"] = "9999"
    os.environ["DEFAULT_LLM_MODEL"] = "gpt-test"
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["DIFY_API_KEY"] = "test-key"
    os.environ["DIFY_URL"] = "https://example.com"

    from app import create_app
    from flask_migrate import upgrade

    app = create_app()

    with app.app_context():
        # Allow skipping DB migrations in CI/unit-only runs
        if not os.getenv("SKIP_DB_MIGRATIONS_FOR_TESTS"):
            upgrade("migrations")
        else:
            dao.db.create_all()

    yield app

    with app.app_context():
        dao.db.session.remove()
        if os.getenv("DROP_TEST_DB_ON_EXIT"):
            dao.db.drop_all()
    if _test_db_dir is not None:
        shutil.rmtree(_test_db_dir, ignore_errors=True)
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def test_client(app):
    with app.test_client() as client:
        yield client


@pytest.fixture
def token():
    return ""


@pytest.fixture(autouse=True)
def mock_redis_client(monkeypatch, request):
    fake_redis = FakeRedis()
    # test_funcs.py uses its own `@patch` decorators for fine-grained Redis control.
    if "service/config/test_funcs.py" in request.node.nodeid:
        return fake_redis
    monkeypatch.setattr(dao, "redis_client", fake_redis, raising=False)

    module_paths = [
        "flaskr.service.user.phone_flow",
        "flaskr.service.user.email_flow",
        "flaskr.service.user.utils",
        "flaskr.service.user.common",
        "flaskr.service.user.auth.providers.google",
        "flaskr.service.config.funcs",
        "flaskr.service.shifu.funcs",
        "flaskr.service.learn.context_v2",
        "flaskr.service.learn.runscript_v2",
        "flaskr.service.order.funs",
    ]
    for module_path in module_paths:
        module = sys.modules.get(module_path)
        if module is None:
            continue
        if hasattr(module, "redis"):
            monkeypatch.setattr(module, "redis", fake_redis, raising=False)
        if hasattr(module, "redis_client"):
            monkeypatch.setattr(module, "redis_client", fake_redis, raising=False)

    return fake_redis


def _should_skip_llm_mock(request) -> bool:
    return request.node.get_closest_marker("no_mock_llm") is not None


@pytest.fixture(autouse=True)
def mock_llm_calls(monkeypatch, request):
    if _should_skip_llm_mock(request):
        return
    llm = sys.modules.get("flaskr.api.llm")
    if llm is None:
        return
    monkeypatch.setattr(llm, "invoke_llm", fake_invoke_llm, raising=False)
    monkeypatch.setattr(llm, "chat_llm", fake_chat_llm, raising=False)
    monkeypatch.setattr(
        llm, "get_allowed_models", fake_get_allowed_models, raising=False
    )
    monkeypatch.setattr(
        llm, "get_current_models", fake_get_current_models, raising=False
    )


@pytest.fixture(autouse=True)
def isolate_env_for_non_app_tests(request):
    if "app" in request.fixturenames:
        yield
        return
    original = {key: os.environ.get(key) for key in ENV_VARS.keys()}
    for key in ENV_VARS.keys():
        os.environ.pop(key, None)
    yield
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
