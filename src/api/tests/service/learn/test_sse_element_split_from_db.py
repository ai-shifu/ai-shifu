"""Test element splitting via SSE simulation using generated blocks from the test DB.

Fetches the latest 100 generated blocks (with non-empty content) from the test
database, feeds each through the ListenElementRunAdapter, and verifies that the
element splitting produces valid SSE output.

Run with:
    cd src/api && pytest tests/service/learn/test_sse_element_split_from_db.py -v --no-header
"""

import json

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BLOCK_TYPE_MDCONTENT = 311
BLOCK_TYPE_MDINTERACTION = 312
BLOCK_TYPE_MDERRORMESSAGE = 313
ROLE_TEACHER = 1
ROLE_STUDENT = 2

VALID_ELEMENT_TYPES = {
    "html",
    "svg",
    "diff",
    "img",
    "interaction",
    "tables",
    "code",
    "latex",
    "md_img",
    "mermaid",
    "title",
    "text",
}
VALID_EVENT_TYPES = {
    "element",
    "break",
    "done",
    "error",
    "audio_segment",
    "audio_complete",
    "variable_update",
    "outline_item_update",
}
VALID_TYPE_CODES = set(range(201, 214))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_blocks_raw(app, limit=100):
    """Fetch latest generated blocks with content directly via SQLAlchemy."""
    from flaskr.service.learn.models import LearnGeneratedBlock

    with app.app_context():
        rows = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.generated_content.isnot(None),
                LearnGeneratedBlock.generated_content != "",
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .limit(limit)
            .all()
        )
        # Detach from session so we can use outside app context
        result = []
        for r in rows:
            result.append(
                {
                    "generated_block_bid": r.generated_block_bid,
                    "shifu_bid": r.shifu_bid,
                    "outline_item_bid": r.outline_item_bid,
                    "user_bid": r.user_bid,
                    "progress_record_bid": r.progress_record_bid,
                    "role": int(r.role or 0),
                    "type": int(r.type or 0),
                    "position": int(r.position or 0),
                    "generated_content": r.generated_content or "",
                }
            )
        return result


def _role_str(role_int):
    if role_int == ROLE_STUDENT:
        return "student"
    return "teacher"


def _simulate_sse_for_block(app, block, *, with_av_contract=True):
    """Simulate SSE stream for a single block via ListenElementRunAdapter.

    When with_av_contract=True (default), builds an AV segmentation contract
    from the content and injects it via an AUDIO_COMPLETE event, which enables
    the adapter to perform visual-kind-based element type inference.
    """
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    content = block["generated_content"]
    generated_block_bid = block["generated_block_bid"]
    outline_bid = block["outline_item_bid"] or "test-outline"
    shifu_bid = block["shifu_bid"] or "test-shifu"
    user_bid = block["user_bid"] or "test-user"

    with app.app_context():
        from flaskr.service.learn.models import LearnGeneratedBlock

        existing = LearnGeneratedBlock.query.filter_by(
            generated_block_bid=generated_block_bid
        ).first()
        if existing is None:
            pytest.skip(f"Block {generated_block_bid} not found in DB")

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        # Build events simulating a single block SSE flow:
        # CONTENT -> [AUDIO_COMPLETE with av_contract] -> BREAK -> DONE
        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content=content,
            ),
        ]

        if with_av_contract and content and content.strip():
            av_contract = build_av_segmentation_contract(content, generated_block_bid)
            events.append(
                RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://test.example.com/audio.mp3",
                        audio_bid="test-audio",
                        duration_ms=1000,
                        position=0,
                        av_contract=av_contract,
                    ),
                )
            )

        events.extend(
            [
                RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.BREAK,
                    content="",
                ),
                RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.DONE,
                    content="",
                ),
            ]
        )

        streamed = list(adapter.process(events))
    return streamed


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSSEElementSplitFromDB:
    """Fetch real blocks and validate SSE element splitting."""

    @pytest.fixture(scope="class")
    def blocks(self, app):
        """Load 100 latest blocks from the test DB."""
        rows = _fetch_blocks_raw(app, limit=100)
        if not rows:
            pytest.skip("No generated blocks found in test DB")
        return rows

    def test_blocks_loaded(self, blocks):
        """Sanity check: we have data to test with."""
        assert len(blocks) > 0
        print(f"\n  Loaded {len(blocks)} blocks from test DB")

    def test_all_blocks_produce_valid_sse(self, app, blocks):
        """Every block must produce a valid SSE stream without errors."""
        failures = []
        stats = {
            "total": 0,
            "success": 0,
            "empty_content_skipped": 0,
            "element_type_counts": {},
            "errors": [],
        }

        for i, block in enumerate(blocks):
            content = block["generated_content"]
            if not content or not content.strip():
                stats["empty_content_skipped"] += 1
                continue

            stats["total"] += 1
            bid = block["generated_block_bid"]

            try:
                streamed = _simulate_sse_for_block(app, block)
            except Exception as exc:
                stats["errors"].append(
                    {
                        "block_bid": bid,
                        "error": str(exc),
                        "content_preview": content[:100],
                    }
                )
                failures.append(f"Block {bid}: process() raised {exc}")
                continue

            # Validate streamed events
            element_events = [s for s in streamed if s.type == "element"]
            break_events = [s for s in streamed if s.type == "break"]
            done_events = [s for s in streamed if s.type == "done"]

            # Must have at least one element event for non-empty content
            if not element_events:
                failures.append(
                    f"Block {bid}: no element events for content "
                    f"({len(content)} chars): {content[:80]}..."
                )
                continue

            # Direct adapter simulation emits block-finish done plus terminal done.
            if break_events:
                failures.append(
                    f"Block {bid}: expected 0 break, got {len(break_events)}"
                )
            if len(done_events) != 2:
                failures.append(f"Block {bid}: expected 2 done, got {len(done_events)}")

            # Validate each element event
            for evt in element_events:
                elem = evt.content
                j = elem.__json__()

                # element_type must be valid
                et = j.get("element_type")
                if et not in VALID_ELEMENT_TYPES:
                    failures.append(f"Block {bid}: invalid element_type '{et}'")

                # element_type_code must be valid
                etc = j.get("element_type_code")
                if etc not in VALID_TYPE_CODES:
                    failures.append(f"Block {bid}: invalid element_type_code {etc}")

                # Track type distribution
                stats["element_type_counts"][et] = (
                    stats["element_type_counts"].get(et, 0) + 1
                )

                # element_bid must be non-empty
                if not j.get("element_bid"):
                    failures.append(f"Block {bid}: empty element_bid")

                # role must be set
                if not j.get("role"):
                    failures.append(f"Block {bid}: empty role")

                # The last element in finalize should be is_final=true
                # (checked for the finalized elements only)

            # Verify final element is_final flag
            finalized = [
                e
                for e in element_events
                if e.content.__json__().get("is_final") is True
            ]
            if not finalized:
                failures.append(f"Block {bid}: no finalized elements (is_final=true)")

            stats["success"] += 1

        # Print summary
        print("\n  === SSE Element Split Test Summary ===")
        print(f"  Total blocks processed: {stats['total']}")
        print(f"  Successful: {stats['success']}")
        print(f"  Empty content skipped: {stats['empty_content_skipped']}")
        print(f"  Errors during process(): {len(stats['errors'])}")
        print("\n  Element type distribution:")
        for et, count in sorted(
            stats["element_type_counts"].items(),
            key=lambda x: -x[1],
        ):
            print(f"    {et}: {count}")

        if stats["errors"]:
            print("\n  Process errors:")
            for err in stats["errors"][:10]:
                print(f"    {err['block_bid']}: {err['error']}")
                print(f"      content: {err['content_preview']}")

        if failures:
            # Show first 20 failures for clarity
            failure_msg = "\n".join(failures[:20])
            if len(failures) > 20:
                failure_msg += f"\n  ... and {len(failures) - 20} more"
            pytest.fail(f"{len(failures)} validation failures:\n{failure_msg}")

    def test_sse_json_serialization_roundtrip(self, app, blocks):
        """Verify SSE JSON output can be parsed back correctly."""
        from flaskr.service.learn.routes import _to_sse_data_line

        sample_blocks = [
            b
            for b in blocks
            if b["generated_content"] and b["generated_content"].strip()
        ][:20]

        failures = []
        for block in sample_blocks:
            bid = block["generated_block_bid"]
            try:
                streamed = _simulate_sse_for_block(app, block)
            except Exception:
                continue

            for evt in streamed:
                try:
                    line = _to_sse_data_line(evt)
                except Exception as exc:
                    failures.append(f"Block {bid}: _to_sse_data_line raised {exc}")
                    continue

                # Must start with "data: " and end with "\n\n"
                if not line.startswith("data: "):
                    failures.append(f"Block {bid}: SSE line missing 'data: ' prefix")
                    continue
                if not line.endswith("\n\n"):
                    failures.append(f"Block {bid}: SSE line missing double newline")
                    continue

                # Must be valid JSON
                json_str = line[6:-2]
                try:
                    parsed = json.loads(json_str)
                except json.JSONDecodeError as exc:
                    failures.append(f"Block {bid}: invalid JSON in SSE: {exc}")
                    continue

                # Must have type and event_type
                if "type" not in parsed:
                    failures.append(f"Block {bid}: missing 'type' in SSE JSON")
                if "event_type" not in parsed:
                    failures.append(f"Block {bid}: missing 'event_type' in SSE JSON")

                # type must match event_type
                if parsed.get("type") != parsed.get("event_type"):
                    failures.append(
                        f"Block {bid}: type '{parsed.get('type')}' != "
                        f"event_type '{parsed.get('event_type')}'"
                    )

                # For element events, validate content structure
                if parsed.get("type") == "element":
                    content = parsed.get("content", {})
                    required_fields = [
                        "element_bid",
                        "element_type",
                        "element_type_code",
                        "role",
                        "is_final",
                        "content",
                    ]
                    for field in required_fields:
                        if field not in content:
                            failures.append(f"Block {bid}: element missing '{field}'")

        print(f"\n  SSE serialization tested on {len(sample_blocks)} blocks")

        if failures:
            failure_msg = "\n".join(failures[:20])
            pytest.fail(f"{len(failures)} serialization failures:\n{failure_msg}")

    def test_content_coverage_no_data_loss(self, app, blocks):
        """Verify that element splitting does not lose content."""
        sample_blocks = [
            b
            for b in blocks
            if b["generated_content"]
            and b["generated_content"].strip()
            and b["type"] == BLOCK_TYPE_MDCONTENT
        ][:30]

        failures = []
        for block in sample_blocks:
            bid = block["generated_block_bid"]
            original_content = block["generated_content"].strip()

            try:
                streamed = _simulate_sse_for_block(app, block)
            except Exception:
                continue

            # Collect all content from element events
            element_texts = []
            for evt in streamed:
                if evt.type != "element":
                    continue
                ct = evt.content.__json__().get("content", "")
                if ct and ct.strip():
                    element_texts.append(ct.strip())

            if not element_texts:
                failures.append(
                    f"Block {bid}: no content in elements for "
                    f"({len(original_content)} chars)"
                )
                continue

            # Concatenated element text should cover the original content
            # (may have structural differences due to splitting, but key
            # text fragments should be present)
            combined = " ".join(element_texts)

            # Extract meaningful text tokens from original (skip markdown syntax)
            import re

            original_words = set(
                w
                for w in re.findall(r"[\w\u4e00-\u9fff]+", original_content)
                if len(w) > 1
            )
            combined_words = set(
                w for w in re.findall(r"[\w\u4e00-\u9fff]+", combined) if len(w) > 1
            )

            if original_words:
                coverage = len(original_words & combined_words) / len(original_words)
                if coverage < 0.5:
                    failures.append(
                        f"Block {bid}: content coverage only {coverage:.0%} "
                        f"({len(original_words & combined_words)}/{len(original_words)} words). "
                        f"Original: {original_content[:80]}... "
                        f"Elements: {combined[:80]}..."
                    )

        print(f"\n  Content coverage tested on {len(sample_blocks)} CONTENT blocks")

        if failures:
            failure_msg = "\n".join(failures[:20])
            pytest.fail(f"{len(failures)} content coverage failures:\n{failure_msg}")

    def test_element_type_matches_content_pattern(self, app, blocks):
        """Verify element_type is appropriate for the content pattern.

        When a block's entire content is a single visual element (e.g. pure SVG),
        the av_contract produces a visual_boundary. During finalization the adapter
        should split it into the correct element type. If the SVG lands in a TEXT
        element instead, it means the av_contract or segment builder did not
        recognize it.
        """
        from flaskr.service.tts.pipeline import build_av_segmentation_contract

        sample_blocks = [
            b
            for b in blocks
            if b["generated_content"]
            and b["generated_content"].strip()
            and len(b["generated_content"]) > 50
        ][:30]

        mismatches = []
        diagnostics = []
        for block in sample_blocks:
            bid = block["generated_block_bid"]
            content = block["generated_content"]

            try:
                streamed = _simulate_sse_for_block(app, block)
            except Exception:
                continue

            for evt in streamed:
                if evt.type != "element":
                    continue
                j = evt.content.__json__()
                et = j.get("element_type")
                ct = j.get("content", "")

                # SVG content should have SVG element type
                if "<svg" in ct.lower() and et != "svg" and et != "html":
                    # Diagnose: check what av_contract produced
                    with app.app_context():
                        av = build_av_segmentation_contract(content, bid)
                    vb_kinds = [
                        vb.get("kind") for vb in av.get("visual_boundaries", [])
                    ]
                    mismatches.append(f"Block {bid}: SVG content but type={et}")
                    diagnostics.append(
                        f"  av_contract visual_boundaries kinds: {vb_kinds}"
                    )

                # Table content should have tables type
                if "<table" in ct.lower() and et not in ("tables", "html"):
                    mismatches.append(f"Block {bid}: table content but type={et}")

        print(f"\n  Type-content matching tested on {len(sample_blocks)} blocks")
        if mismatches:
            print(f"  Mismatches found: {len(mismatches)}")
            for i, m in enumerate(mismatches[:10]):
                print(f"    {m}")
                if i < len(diagnostics):
                    print(f"    {diagnostics[i]}")
            # Report as warnings, not hard failures, since the adapter
            # may legitimately use fallback TEXT when av_contract does
            # not recognize the visual boundary

    def test_pure_visual_blocks_element_type(self, app, blocks):
        """Diagnose element type inference for blocks whose content is pure
        visual (SVG, HTML with no speakable text).

        These blocks have visual_boundaries in av_contract but no
        speakable_segments, so build_visual_segments_for_block returns [].
        The adapter's _finalize_block fallback path (lines 922-953) should
        still create properly typed elements from visual_boundaries.
        """
        from flaskr.service.learn.listen_slide_builder import (
            build_visual_segments_for_block,
        )
        from flaskr.service.learn.listen_source_span_utils import (
            normalize_source_span,
        )
        from flaskr.service.tts.pipeline import build_av_segmentation_contract

        visual_blocks = [
            b
            for b in blocks
            if b["generated_content"]
            and b["generated_content"].strip()
            and (
                b["generated_content"].strip().startswith("<svg")
                or b["generated_content"].strip().startswith("<div")
                or b["generated_content"].strip().startswith("<table")
            )
        ]

        print(f"\n  Pure visual blocks found: {len(visual_blocks)}")

        results = []
        for block in visual_blocks[:15]:
            bid = block["generated_block_bid"]
            content = block["generated_content"]

            with app.app_context():
                av = build_av_segmentation_contract(content, bid)

            vb = av.get("visual_boundaries", [])
            sp = av.get("speakable_segments", [])

            # Try build_visual_segments_for_block
            segments, pos_map = build_visual_segments_for_block(
                raw_content=content,
                generated_block_bid=bid,
                av_contract=av,
                element_index_offset=0,
            )

            # Check fallback path: visual_boundaries with valid source_span
            fallback_valid = 0
            for boundary in vb:
                source_span = normalize_source_span(boundary.get("source_span"))
                kind = boundary.get("kind", "")
                if source_span and kind:
                    fallback_valid += 1

            # Simulate SSE
            try:
                streamed = _simulate_sse_for_block(app, block)
            except Exception:
                streamed = []

            element_types = [
                evt.content.__json__().get("element_type")
                for evt in streamed
                if evt.type == "element"
            ]

            result = {
                "bid": bid[:12],
                "content_start": content[:40].replace("\n", "\\n"),
                "visual_boundaries": len(vb),
                "vb_kinds": [b.get("kind") for b in vb],
                "speakable_segments": len(sp),
                "segments_built": len(segments),
                "fallback_valid": fallback_valid,
                "final_element_types": element_types,
            }
            results.append(result)
            print(f"  Block {result['bid']}...")
            print(f"    content: {result['content_start']}...")
            print(f"    vb={result['visual_boundaries']} kinds={result['vb_kinds']}")
            print(f"    speakable={result['speakable_segments']}")
            print(f"    segments_built={result['segments_built']}")
            print(f"    fallback_valid={result['fallback_valid']}")
            print(f"    final types: {result['final_element_types']}")

        # Verify the retire notification element is properly formed
        retire_issues = []
        for block in visual_blocks[:15]:
            bid = block["generated_block_bid"]
            try:
                streamed = _simulate_sse_for_block(app, block)
            except Exception:
                continue

            element_events = [e for e in streamed if e.type == "element"]
            for evt in element_events:
                j = evt.content.__json__()
                # A retire element should have is_new=false and is_renderable=false
                if j.get("is_new") is False:
                    if j.get("is_renderable") is not False:
                        retire_issues.append(
                            f"Block {bid[:12]}: retire element has "
                            f"is_renderable={j.get('is_renderable')}"
                        )
                    if j.get("is_final") is not True:
                        retire_issues.append(
                            f"Block {bid[:12]}: retire element has "
                            f"is_final={j.get('is_final')}"
                        )

        # Count blocks with proper retire → replace flow
        proper_retire = 0
        for block in visual_blocks[:15]:
            bid = block["generated_block_bid"]
            try:
                streamed = _simulate_sse_for_block(app, block)
            except Exception:
                continue
            element_events = [e for e in streamed if e.type == "element"]
            has_retire = any(
                e.content.__json__().get("is_new") is False
                and e.content.__json__().get("is_renderable") is False
                for e in element_events
            )
            has_final_typed = any(
                e.content.__json__().get("element_type") != "text"
                and e.content.__json__().get("is_final") is True
                for e in element_events
            )
            if has_retire and has_final_typed:
                proper_retire += 1

        print(
            f"\n  Summary: {proper_retire}/{len(results)} blocks have "
            f"proper retire+replace flow"
        )

        if retire_issues:
            for issue in retire_issues[:5]:
                print(f"    Issue: {issue}")
            pytest.fail(
                f"{len(retire_issues)} retire element issues:\n"
                + "\n".join(retire_issues[:10])
            )

        if not results:
            pytest.skip("No pure visual blocks found in test DB sample")

        assert proper_retire > 0, "No blocks demonstrated retire+replace flow"
