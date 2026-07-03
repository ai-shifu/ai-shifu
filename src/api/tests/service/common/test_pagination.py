"""Tests for the shared pagination normalization helper."""

import pytest

from flaskr.service.common.pagination import (
    DEFAULT_PAGE_INDEX,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    normalize_pagination,
)


def test_constants_keep_admin_defaults():
    assert DEFAULT_PAGE_INDEX == 1
    assert DEFAULT_PAGE_SIZE == 20
    assert MAX_PAGE_SIZE == 100


@pytest.mark.parametrize(
    ("page_index", "page_size", "expected"),
    [
        (1, 20, (1, 20)),
        (3, 50, (3, 50)),
        # falsy inputs fall back to the defaults
        (None, None, (DEFAULT_PAGE_INDEX, DEFAULT_PAGE_SIZE)),
        (0, 0, (DEFAULT_PAGE_INDEX, DEFAULT_PAGE_SIZE)),
        ("", "", (DEFAULT_PAGE_INDEX, DEFAULT_PAGE_SIZE)),
        # page index below 1 is clamped to 1
        (-5, 10, (1, 10)),
        # page size below 1 is clamped to 1
        (2, -3, (2, 1)),
        # page size above the cap is clamped to MAX_PAGE_SIZE
        (1, 999, (1, MAX_PAGE_SIZE)),
        (1, MAX_PAGE_SIZE + 1, (1, MAX_PAGE_SIZE)),
        # numeric strings are coerced
        ("2", "30", (2, 30)),
        # non-numeric input falls back to the defaults
        ("abc", "xyz", (DEFAULT_PAGE_INDEX, DEFAULT_PAGE_SIZE)),
        ([], {}, (DEFAULT_PAGE_INDEX, DEFAULT_PAGE_SIZE)),
        # mixed: bad index, valid size
        ("abc", 40, (DEFAULT_PAGE_INDEX, 40)),
        # floats truncate through int()
        (2.9, 30.7, (2, 30)),
    ],
)
def test_normalize_pagination(page_index, page_size, expected):
    assert normalize_pagination(page_index, page_size) == expected
