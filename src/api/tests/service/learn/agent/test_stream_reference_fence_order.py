"""An earlier native fence wins over a later unfinished reference marker."""

import pytest
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_reference_marker_wait_does_not_hide_an_earlier_native_fence(
    ending: str,
) -> None:
    source = ending.join(["[r]: {{", "```", "?[A|B]}}?[%{{ outer }} C|D]"])
    streams = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for chunks in streams:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in chunks) + syntax.flush()
        assert shown == source, chunks
        assert syntax.spans == [], chunks
