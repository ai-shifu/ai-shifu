import pytest
from flaskr.command.unified_migration_task import _quote_identifier


@pytest.mark.parametrize("name", ["learn_progress_records", "_bid", "Col1"])
def test_quote_identifier_quotes_valid_names(name):
    assert _quote_identifier(name) == f"`{name}`"


@pytest.mark.parametrize(
    "name", ["", "1table", "users; drop table users", "user`s", "learn progress"]
)
def test_quote_identifier_rejects_unsafe_names(name):
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _quote_identifier(name)
