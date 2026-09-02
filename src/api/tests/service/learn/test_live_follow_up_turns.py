"""Playback-aware reconciliation tests for Gemini Live follow-up turns."""

from __future__ import annotations

from flaskr.service.learn.gemini_live_provider import GeminiLiveServerEvent
from flaskr.service.learn.live_follow_up_turns import (
    LiveTurnAccumulator,
    merge_live_transcript,
)


def test_accumulator_merges_cumulative_transcripts_and_waits_500ms() -> None:
    accumulator = LiveTurnAccumulator("session-1")
    accumulator.process_event(
        GeminiLiveServerEvent(input_transcripts=("Hel",)),
        now=1.0,
    )
    result = accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("Hello",),
            output_transcripts=("Hi",),
            audio_chunks=(b"abcd",),
            usage_metadata={"totalTokenCount": 8},
        ),
        now=1.1,
    )

    assert result.audio_turn_index == 1
    assert [update.text for update in result.transcript_updates] == ["Hi", "Hello"]
    accumulator.record_audio_sent(1, len(result.audio_chunks[0]))
    accumulator.record_playback_progress(1, 4)
    terminal = accumulator.process_event(
        GeminiLiveServerEvent(turn_complete=True),
        now=2.0,
    )

    assert terminal.terminal_turn_index == 1
    assert accumulator.pop_ready(now=2.499) == []
    commits = accumulator.pop_ready(now=2.5)
    assert len(commits) == 1
    assert commits[0].user_transcript == "Hello"
    assert commits[0].answer_transcript == "Hi"
    assert commits[0].full_answer_transcript == "Hi"
    assert commits[0].usage_metadata == {"totalTokenCount": 8}
    assert commits[0].terminal_reason == "turn_complete"
    assert commits[0].has_final_user_transcript is True


def test_interim_input_transcription_replaces_hypothesis_without_persisting() -> None:
    accumulator = LiveTurnAccumulator("session-interim")

    first = accumulator.process_event(
        GeminiLiveServerEvent(interim_input_transcripts=("I scream",)),
        now=1.0,
    )
    revised = accumulator.process_event(
        GeminiLiveServerEvent(interim_input_transcripts=("ice cream",)),
        now=1.1,
    )
    accumulator.process_event(GeminiLiveServerEvent(turn_complete=True), now=1.2)

    assert [(item.text, item.final) for item in first.transcript_updates] == [
        ("I scream", False)
    ]
    assert [(item.text, item.final) for item in revised.transcript_updates] == [
        ("ice cream", False)
    ]
    assert accumulator.finish_session(now=1.3) == []


def test_final_input_transcription_wins_over_late_interim_snapshot() -> None:
    accumulator = LiveTurnAccumulator("session-interim-final")
    accumulator.process_event(
        GeminiLiveServerEvent(interim_input_transcripts=("weather two day",)),
        now=1.0,
    )
    final = accumulator.process_event(
        GeminiLiveServerEvent(input_transcripts=("weather today",)),
        now=1.1,
    )
    stale = accumulator.process_event(
        GeminiLiveServerEvent(interim_input_transcripts=("weather to date",)),
        now=1.2,
    )
    accumulator.process_event(GeminiLiveServerEvent(turn_complete=True), now=1.3)

    assert [item.text for item in final.transcript_updates] == ["weather today"]
    assert stale.transcript_updates == ()
    assert accumulator.pop_ready(now=1.8)[0].user_transcript == "weather today"


def test_completed_turn_waits_for_browser_playback_after_reconciliation() -> None:
    accumulator = LiveTurnAccumulator("session-playback")
    result = accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("Question",),
            output_transcripts=("A longer answer",),
            audio_chunks=(b"a" * 4000,),
            turn_complete=True,
        ),
        now=1.0,
    )
    accumulator.record_audio_sent(1, len(result.audio_chunks[0]))
    accumulator.record_playback_progress(1, 1000)

    assert accumulator.pop_ready(now=1.5) == []
    assert accumulator.pop_ready(now=20.0) == []

    accumulator.mark_playback_complete(1)
    commit = accumulator.pop_ready(now=20.0)[0]
    assert commit.answer_transcript == "A longer answer"
    assert commit.audio_played_bytes == 4000


def test_new_audio_invalidates_an_early_playback_complete_signal() -> None:
    accumulator = LiveTurnAccumulator("session-more-audio")
    first = accumulator.process_event(
        GeminiLiveServerEvent(
            output_transcripts=("First",),
            audio_chunks=(b"a" * 100,),
        ),
        now=1.0,
    )
    accumulator.record_audio_sent(1, len(first.audio_chunks[0]))
    accumulator.mark_playback_complete(1)
    second = accumulator.process_event(
        GeminiLiveServerEvent(
            output_transcripts=("First second",),
            audio_chunks=(b"b" * 100,),
            turn_complete=True,
        ),
        now=1.1,
    )
    accumulator.record_audio_sent(1, len(second.audio_chunks[0]))

    assert accumulator.pop_ready(now=1.6) == []
    accumulator.mark_playback_complete(1)
    assert accumulator.pop_ready(now=1.6)[0].answer_transcript == "First second"


def test_interruption_commits_only_transcript_checkpoint_already_played() -> None:
    accumulator = LiveTurnAccumulator("session-1")
    first = accumulator.process_event(
        GeminiLiveServerEvent(
            output_transcripts=("Hello",),
            audio_chunks=(b"a" * 100,),
        ),
        now=1.0,
    )
    accumulator.record_audio_sent(1, len(first.audio_chunks[0]))
    second = accumulator.process_event(
        GeminiLiveServerEvent(
            output_transcripts=("Hello there",),
            audio_chunks=(b"b" * 100,),
        ),
        now=1.1,
    )
    accumulator.record_audio_sent(1, len(second.audio_chunks[0]))
    accumulator.record_playback_progress(1, 110)

    interrupted = accumulator.process_event(
        GeminiLiveServerEvent(interrupted=True),
        now=2.0,
    )

    assert interrupted.interrupted_turn_index == 1
    commit = accumulator.pop_ready(now=2.5)[0]
    assert commit.interrupted is True
    assert commit.answer_transcript == "Hello"
    assert commit.full_answer_transcript == "Hello there"
    assert commit.audio_sent_bytes == 200
    assert commit.audio_played_bytes == 110


def test_multipart_event_binds_transcript_after_all_event_audio_is_sent() -> None:
    accumulator = LiveTurnAccumulator("session-1")
    result = accumulator.process_event(
        GeminiLiveServerEvent(
            output_transcripts=("Whole phrase",),
            audio_chunks=(b"a" * 50, b"b" * 50),
        ),
        now=1.0,
    )
    accumulator.record_audio_sent(1, 50)
    accumulator.record_playback_progress(1, 50)
    accumulator.process_event(
        GeminiLiveServerEvent(interrupted=True),
        now=1.1,
    )

    commit = accumulator.pop_ready(now=1.6)[0]
    assert result.audio_turn_index == 1
    assert commit.answer_transcript == ""
    assert commit.full_answer_transcript == "Whole phrase"


def test_transcript_before_audio_is_bound_after_the_complete_audio_event() -> None:
    accumulator = LiveTurnAccumulator("session-reordered-output")
    accumulator.process_event(
        GeminiLiveServerEvent(output_transcripts=("Spoken answer",)),
        now=1.0,
    )
    audio = accumulator.process_event(
        GeminiLiveServerEvent(audio_chunks=(b"a" * 50, b"b" * 50)),
        now=1.1,
    )
    accumulator.record_audio_sent(1, 50)
    accumulator.record_audio_sent(1, 50)
    accumulator.finish_audio_event(1)
    accumulator.record_playback_progress(1, 100)
    accumulator.process_event(
        GeminiLiveServerEvent(interrupted=True),
        now=1.2,
    )

    commit = accumulator.pop_ready(now=1.7)[0]
    assert audio.audio_turn_index == 1
    assert commit.answer_transcript == "Spoken answer"
    assert commit.audio_played_bytes == 100


def test_late_output_transcript_reconciles_into_previous_terminal_turn() -> None:
    accumulator = LiveTurnAccumulator("session-1")
    result = accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("Question",),
            output_transcripts=("Good",),
            audio_chunks=(b"x" * 10,),
        ),
        now=5.0,
    )
    accumulator.record_audio_sent(1, len(result.audio_chunks[0]))
    accumulator.record_playback_progress(1, 10)
    accumulator.process_event(
        GeminiLiveServerEvent(turn_complete=True),
        now=6.0,
    )

    late = accumulator.process_event(
        GeminiLiveServerEvent(output_transcripts=("Good day",)),
        now=6.2,
    )

    assert late.transcript_updates[0].turn_index == 1
    assert late.transcript_updates[0].final is True
    assert accumulator.pop_ready(now=6.49) == []
    commit = accumulator.pop_ready(now=6.5)[0]
    assert commit.answer_transcript == "Good day"


def test_late_input_output_and_usage_update_terminal_turn_without_extending_window() -> (
    None
):
    accumulator = LiveTurnAccumulator("session-1")
    accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("Question",),
            output_transcripts=("Answer",),
            usage_metadata={"totalTokenCount": 2},
            turn_complete=True,
        ),
        now=4.0,
    )

    late = accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("Question complete",),
            output_transcripts=("Answer complete",),
            usage_metadata={"totalTokenCount": 6},
        ),
        now=4.2,
    )

    assert [
        (update.role, update.turn_index, update.final)
        for update in late.transcript_updates
    ] == [
        ("assistant", 1, True),
        ("user", 1, True),
    ]
    assert accumulator.ready_at(1) == 4.5
    commit = accumulator.pop_ready(now=4.5)[0]
    assert commit.user_transcript == "Question complete"
    assert commit.full_answer_transcript == "Answer complete"
    assert commit.usage_metadata == {"totalTokenCount": 6}


def test_unrelated_input_within_reconciliation_window_starts_next_turn() -> None:
    accumulator = LiveTurnAccumulator("session-1")
    accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("First question",),
            output_transcripts=("First answer",),
            usage_metadata={"totalTokenCount": 2},
            turn_complete=True,
        ),
        now=1.0,
    )

    next_turn = accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("A different question",),
            output_transcripts=("Second answer",),
        ),
        now=1.1,
    )

    assert {
        (update.role, update.turn_index, update.final)
        for update in next_turn.transcript_updates
    } == {
        ("assistant", 2, False),
        ("user", 2, False),
    }


def test_barge_in_event_finalizes_old_turn_and_starts_new_user_turn() -> None:
    accumulator = LiveTurnAccumulator("session-1")
    result = accumulator.process_event(
        GeminiLiveServerEvent(
            output_transcripts=("First answer",),
            input_transcripts=("Second question",),
            interrupted=True,
        ),
        now=3.0,
    )

    assert result.interrupted_turn_index == 1
    assert [
        (update.role, update.turn_index, update.final)
        for update in result.transcript_updates
    ] == [
        ("assistant", 1, False),
        ("assistant", 1, True),
        ("user", 2, False),
    ]
    assert accumulator.active_turn_index == 2

    next_result = accumulator.process_event(
        GeminiLiveServerEvent(output_transcripts=("Second answer",)),
        now=3.1,
    )
    assert next_result.transcript_updates[0].turn_index == 2


def test_barge_in_trailing_turn_complete_does_not_finish_the_new_turn() -> None:
    accumulator = LiveTurnAccumulator("session-barge-in-completion")
    accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("First question",),
            output_transcripts=("First answer",),
            audio_chunks=(b"a" * 20,),
        ),
        now=1.0,
    )
    interrupted = accumulator.process_event(
        GeminiLiveServerEvent(
            input_transcripts=("Second question",),
            interrupted=True,
        ),
        now=1.1,
    )

    trailing = accumulator.process_event(
        GeminiLiveServerEvent(
            turn_complete=True,
            usage_metadata={"totalTokenCount": 5},
        ),
        now=1.2,
    )
    second_answer = accumulator.process_event(
        GeminiLiveServerEvent(
            output_transcripts=("Second answer",),
            turn_complete=True,
        ),
        now=1.3,
    )

    assert interrupted.interrupted_turn_index == 1
    assert trailing.terminal_turn_index is None
    assert second_answer.terminal_turn_index == 2
    commits = accumulator.pop_ready(now=1.8)
    assert [
        (commit.turn_index, commit.user_transcript, commit.interrupted)
        for commit in commits
    ] == [
        (1, "First question", True),
        (2, "Second question", False),
    ]
    assert commits[0].usage_metadata == {"totalTokenCount": 5}
    assert commits[1].full_answer_transcript == "Second answer"


def test_usage_without_final_user_transcript_is_still_committable() -> None:
    accumulator = LiveTurnAccumulator("session-1")
    accumulator.process_event(
        GeminiLiveServerEvent(
            usage_metadata={"promptTokenCount": 4},
            turn_complete=True,
        ),
        now=10.0,
    )

    commit = accumulator.pop_ready(now=10.5)[0]
    assert commit.user_transcript == ""
    assert commit.has_final_user_transcript is False
    assert commit.usage_metadata == {"promptTokenCount": 4}


def test_finish_session_forces_active_and_pending_turns() -> None:
    accumulator = LiveTurnAccumulator("session-1")
    accumulator.process_event(
        GeminiLiveServerEvent(input_transcripts=("unfinished",)),
        now=1.0,
    )

    commits = accumulator.finish_session(now=1.1)

    assert len(commits) == 1
    assert commits[0].terminal_reason == "session_end"
    assert commits[0].user_transcript == ""
    assert commits[0].has_final_user_transcript is False


def test_transcript_merge_handles_delta_cumulative_overlap_and_stale_prefix() -> None:
    assert merge_live_transcript("", "Hello") == "Hello"
    assert merge_live_transcript("Hel", "Hello") == "Hello"
    assert merge_live_transcript("Hello", "Hel") == "Hello"
    assert merge_live_transcript("Hello wor", "world") == "Hello world"
    assert merge_live_transcript("world", "Hello world") == "Hello world"
    assert merge_live_transcript("Hello", " there") == "Hello there"
