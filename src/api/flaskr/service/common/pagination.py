"""Shared pagination normalization for admin/operator list endpoints.

Consolidates the byte-identical helpers that previously lived in
``flaskr/service/referral/admin.py`` (``_normalize_page``),
``flaskr/service/referral/campaign_admin.py`` (``_normalize_page``), and
``flaskr/service/billing/queries.py`` (``normalize_pagination``).
"""

from __future__ import annotations

DEFAULT_PAGE_INDEX = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def normalize_pagination(page_index: int, page_size: int) -> tuple[int, int]:
    """Normalize list pagination parameters to the shared admin defaults.

    Falsy or non-integer inputs fall back to the defaults, the page index is
    clamped to at least 1, and the page size is clamped to
    ``1..MAX_PAGE_SIZE``.
    """
    try:
        safe_page_index = max(int(page_index or DEFAULT_PAGE_INDEX), 1)
    except (TypeError, ValueError):
        safe_page_index = DEFAULT_PAGE_INDEX
    try:
        safe_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    except (TypeError, ValueError):
        safe_page_size = DEFAULT_PAGE_SIZE
    return safe_page_index, min(safe_page_size, MAX_PAGE_SIZE)
