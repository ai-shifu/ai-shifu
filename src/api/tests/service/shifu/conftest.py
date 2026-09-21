"""Keep forwarded admin test patches isolated across course service tests."""

from collections.abc import Iterator

import pytest
from flaskr.service.shifu import admin
from flaskr.service.shifu.admin_operations import courses


@pytest.fixture(autouse=True)
def restore_admin_forwarded_bindings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The compatibility facades forward setattr to multiple implementations.
    # Undoing a facade patch alone restores its value into every child, even
    # when those children originally had different functions with that name.
    snapshots = {}
    for facade, children in (
        (admin, admin._ADMIN_SPLIT_SUBMODULES),
        (courses, courses._COURSES_SPLIT_SUBMODULES),
    ):
        for child in children:
            snapshots[child] = {
                name: value
                for name, value in vars(child).items()
                if name in vars(facade)
            }
    snapshots[courses] = {
        name: value
        for name, value in vars(courses).items()
        if name in admin._OPERATOR_COURSE_FORWARDABLE_NAMES
    }
    yield
    monkeypatch.undo()
    for module, original in snapshots.items():
        # Bypass compatibility forwarding when restoring each module's own value.
        vars(module).update(original)
