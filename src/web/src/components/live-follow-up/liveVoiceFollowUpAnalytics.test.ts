import {
  buildLiveVoiceFollowUpTextAnalytics,
  buildLiveVoiceFollowUpMicrophoneAnalytics,
  buildLiveVoiceFollowUpPauseAnalytics,
  buildLiveVoiceFollowUpResumeAnalytics,
  LIVE_VOICE_FOLLOW_UP_TEXT_SUBMIT_EVENT,
  LIVE_VOICE_FOLLOW_UP_MICROPHONE_RESULT_EVENT,
  LIVE_VOICE_FOLLOW_UP_PAUSE_EVENT,
  LIVE_VOICE_FOLLOW_UP_PAUSE_REASONS,
  LIVE_VOICE_FOLLOW_UP_RESUME_EVENT,
  buildLiveVoiceFollowUpAttemptAnalytics,
  buildLiveVoiceFollowUpResultAnalytics,
  buildLiveVoiceFollowUpSessionEndAnalytics,
  normalizeLiveVoiceFollowUpEndReason,
  normalizeLiveVoiceFollowUpErrorCode,
  shouldTrackLiveVoiceFollowUp,
  LIVE_VOICE_FOLLOW_UP_ATTEMPT_EVENT,
  LIVE_VOICE_FOLLOW_UP_END_REASONS,
  LIVE_VOICE_FOLLOW_UP_ERROR_CODES,
  LIVE_VOICE_FOLLOW_UP_RESULT_EVENT,
  LIVE_VOICE_FOLLOW_UP_SESSION_END_EVENT,
} from './liveVoiceFollowUpAnalytics';

const baseInput = {
  shifuBid: 'course-1',
  outlineBid: 'lesson-1',
  learningMode: 'listen' as const,
  surface: 'listen_player' as const,
};

it('allowlists new typed-input and microphone operation events', () => {
  expect(LIVE_VOICE_FOLLOW_UP_TEXT_SUBMIT_EVENT).toBe(
    'learner_voice_follow_up_text_submit',
  );
  expect(LIVE_VOICE_FOLLOW_UP_MICROPHONE_RESULT_EVENT).toBe(
    'learner_voice_follow_up_microphone_result',
  );
  const extra = {
    ...baseInput,
    prompt: 'private',
    text: 'question',
    model: 'model',
    voice: 'voice',
    token: 'secret',
    url: 'https://private.invalid',
  };
  const text = buildLiveVoiceFollowUpTextAnalytics({
    ...extra,
    submissionMethod: 'keyboard',
    interrupted: true,
  });
  expect(text).toEqual({
    shifu_bid: 'course-1',
    outline_bid: 'lesson-1',
    learning_mode: 'listen',
    surface: 'listen_player',
    submission_method: 'keyboard',
    interrupted: true,
  });
  expectNoProhibitedFields(text);
  for (const outcome of ['success', 'failed', 'cancelled'] as const) {
    const microphone = buildLiveVoiceFollowUpMicrophoneAnalytics({
      ...extra,
      enabled: true,
      outcome,
      errorCode: 'microphone_denied',
    });
    expect(microphone).toEqual({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      learning_mode: 'listen',
      surface: 'listen_player',
      enabled: true,
      outcome,
      error_code: 'microphone_denied',
    });
    expectNoProhibitedFields(microphone);
  }
});

const prohibitedFields = [
  'model',
  'voice',
  'voice_id',
  'audio',
  'transcript',
  'prompt',
  'anchor_element_bid',
  'live_session_bid',
  'session_bid',
  'ws_path',
  'url',
  'ticket',
  'token',
  'api_key',
  'error',
  'error_message',
  'provider_response',
] as const;

const expectNoProhibitedFields = (payload: Record<string, unknown>) => {
  prohibitedFields.forEach(field => {
    expect(payload).not.toHaveProperty(field);
  });
};

describe('live voice follow-up analytics contract', () => {
  it('allowlists pause reasons and resume dimensions without private input', () => {
    expect(LIVE_VOICE_FOLLOW_UP_PAUSE_EVENT).toBe(
      'learner_voice_follow_up_pause',
    );
    expect(LIVE_VOICE_FOLLOW_UP_RESUME_EVENT).toBe(
      'learner_voice_follow_up_resume',
    );
    expect(LIVE_VOICE_FOLLOW_UP_PAUSE_REASONS).toEqual([
      'panel_closed',
      'page_hidden',
      'audio_replaced',
    ]);
    const extra = {
      ...baseInput,
      prompt: 'private',
      text: 'private question',
      model: 'private model',
      voice: 'private voice',
      token: 'private credential',
      url: 'https://private.invalid',
      reason: 'panel_closed' as const,
    };
    for (const reason of LIVE_VOICE_FOLLOW_UP_PAUSE_REASONS) {
      const pause = buildLiveVoiceFollowUpPauseAnalytics({ ...extra, reason });
      expect(pause).toEqual({
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'listen',
        surface: 'listen_player',
        reason,
      });
      expectNoProhibitedFields(pause);
    }
    const resume = buildLiveVoiceFollowUpResumeAnalytics(extra);
    expect(resume).toEqual({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      learning_mode: 'listen',
      surface: 'listen_player',
    });
    expectNoProhibitedFields(resume);
  });

  it('supports the documented aggregate consumer without counting microphone-off as adoption', () => {
    const attempts = Array.from({ length: 3 }, () =>
      buildLiveVoiceFollowUpAttemptAnalytics(baseInput),
    );
    const results = (['success', 'success', 'failed'] as const).map(outcome =>
      buildLiveVoiceFollowUpResultAnalytics({
        ...baseInput,
        outcome,
        errorCode: 'none',
      }),
    );
    const text = (['keyboard', 'button'] as const).map(submissionMethod =>
      buildLiveVoiceFollowUpTextAnalytics({
        ...baseInput,
        submissionMethod,
        interrupted: submissionMethod === 'button',
      }),
    );
    const microphone = (['success', 'failed', 'cancelled'] as const).map(
      outcome =>
        buildLiveVoiceFollowUpMicrophoneAnalytics({
          ...baseInput,
          enabled: true,
          outcome,
          errorCode: 'none',
        }),
    );
    microphone.push(
      buildLiveVoiceFollowUpMicrophoneAnalytics({
        ...baseInput,
        enabled: false,
        outcome: 'success',
        errorCode: 'none',
      }),
    );
    const ends = [true, false].map(hadExchange =>
      buildLiveVoiceFollowUpSessionEndAnalytics({
        ...baseInput,
        hadExchange,
        durationMs: 1000,
        endReason: 'user_end',
      }),
    );
    const pauses = (['panel_closed', 'page_hidden'] as const).map(reason =>
      buildLiveVoiceFollowUpPauseAnalytics({ ...baseInput, reason }),
    );
    const resumes = [buildLiveVoiceFollowUpResumeAnalytics(baseInput)];
    expect(text).toHaveLength(2);
    expect(microphone.filter(row => row.enabled)).toHaveLength(3);
    expect(
      microphone.filter(row => row.enabled && row.outcome === 'success'),
    ).toHaveLength(1);
    expect(
      results.filter(row => row.outcome === 'success').length / attempts.length,
    ).toBe(2 / 3);
    expect(ends.filter(row => row.had_exchange).length / ends.length).toBe(
      1 / 2,
    );
    expect(pauses).toHaveLength(2);
    expect(resumes).toHaveLength(1);
    expect(resumes.length / pauses.length).toBe(1 / 2);
    expect(attempts).toHaveLength(3);
    expect(results).toHaveLength(3);
    expect(ends).toHaveLength(2);
  });

  it('uses stable version-one event names', () => {
    expect(LIVE_VOICE_FOLLOW_UP_ATTEMPT_EVENT).toBe(
      'learner_voice_follow_up_attempt',
    );
    expect(LIVE_VOICE_FOLLOW_UP_RESULT_EVENT).toBe(
      'learner_voice_follow_up_result',
    );
    expect(LIVE_VOICE_FOLLOW_UP_SESSION_END_EVENT).toBe(
      'learner_voice_follow_up_session_end',
    );
  });

  it('uses the exact reviewed attempt payload', () => {
    const payload = buildLiveVoiceFollowUpAttemptAnalytics(baseInput);
    expect(payload).toEqual({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      learning_mode: 'listen',
      surface: 'listen_player',
    });
    expect(Object.keys(payload).sort()).toEqual(
      ['learning_mode', 'outline_bid', 'shifu_bid', 'surface'].sort(),
    );
    expectNoProhibitedFields(payload);
  });

  it.each([
    ['success', 'none'],
    ['failed', 'microphone_denied'],
    ['cancelled', 'none'],
  ] as const)('adds only bounded %s result fields', (outcome, errorCode) => {
    const payload = buildLiveVoiceFollowUpResultAnalytics({
      ...baseInput,
      outcome,
      errorCode,
    });
    expect(payload).toEqual({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      learning_mode: 'listen',
      surface: 'listen_player',
      outcome,
      error_code: errorCode,
    });
    expect(Object.keys(payload).sort()).toEqual(
      [
        'error_code',
        'learning_mode',
        'outcome',
        'outline_bid',
        'shifu_bid',
        'surface',
      ].sort(),
    );
    expectNoProhibitedFields(payload);
  });

  it('rounds duration and reports only the reviewed session outcome', () => {
    const payload = buildLiveVoiceFollowUpSessionEndAnalytics({
      ...baseInput,
      durationMs: 1234.6,
      hadExchange: true,
      endReason: 'user_end',
    });
    expect(payload).toEqual({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      learning_mode: 'listen',
      surface: 'listen_player',
      duration_ms: 1235,
      had_exchange: true,
      end_reason: 'user_end',
    });
    expect(Object.keys(payload).sort()).toEqual(
      [
        'duration_ms',
        'end_reason',
        'had_exchange',
        'learning_mode',
        'outline_bid',
        'shifu_bid',
        'surface',
      ].sort(),
    );
    expectNoProhibitedFields(payload);
  });

  it.each([
    [Number.NaN, 0],
    [Number.POSITIVE_INFINITY, 0],
    [-42, 0],
  ])('normalizes non-deliverable duration %s to %s', (durationMs, expected) => {
    expect(
      buildLiveVoiceFollowUpSessionEndAnalytics({
        ...baseInput,
        durationMs,
        hadExchange: false,
        endReason: 'connection_error',
      }).duration_ms,
    ).toBe(expected);
  });

  it('includes guest/member learning and excludes preview and classroom', () => {
    expect(
      shouldTrackLiveVoiceFollowUp({
        previewMode: false,
        learningMode: 'read',
      }),
    ).toBe(true);
    expect(
      shouldTrackLiveVoiceFollowUp({
        previewMode: false,
        learningMode: 'listen',
      }),
    ).toBe(true);
    expect(
      shouldTrackLiveVoiceFollowUp({
        previewMode: true,
        learningMode: 'read',
      }),
    ).toBe(false);
    expect(
      shouldTrackLiveVoiceFollowUp({
        previewMode: false,
        learningMode: 'classroom',
      }),
    ).toBe(false);
  });

  it('bounds untrusted server enums', () => {
    expect(LIVE_VOICE_FOLLOW_UP_ERROR_CODES).toEqual([
      'none',
      'microphone_denied',
      'microphone_unavailable',
      'microphone_busy',
      'audio_unavailable',
      'session_create_failed',
      'session_expired',
      'capacity_exceeded',
      'origin_rejected',
      'configuration_error',
      'network_error',
      'websocket_failed',
      'server_error',
      'unknown',
    ]);
    expect(LIVE_VOICE_FOLLOW_UP_END_REASONS).toEqual([
      'user_end',
      'user_close',
      'timeout',
      'page_hidden',
      'lesson_changed',
      'connection_closed',
      'connection_error',
      'server_end',
      'server_timeout',
      'replaced',
    ]);
    expect(normalizeLiveVoiceFollowUpErrorCode('capacity_reached')).toBe(
      'capacity_exceeded',
    );
    expect(normalizeLiveVoiceFollowUpErrorCode('upstream_unavailable')).toBe(
      'server_error',
    );
    expect(normalizeLiveVoiceFollowUpErrorCode('private upstream error')).toBe(
      'unknown',
    );
    expect(normalizeLiveVoiceFollowUpEndReason('private upstream reason')).toBe(
      'server_end',
    );
  });
});
