import { startDebugRegenerateTracking } from './debug-regenerate-tracking';

describe.each([false, true])('Debug tracking (answerEdit=%s)', answerEdit => {
  const context = {
    anchor: 'private-step-anchor',
    answerEdit,
    shifuBid: 'course-id',
    outlineBid: 'lesson-id',
  };

  it('emits the accepted request before its first terminal result with only allowed fields', () => {
    const trackEvent = jest.fn();
    const finish = startDebugRegenerateTracking({
      ...context,
      trackEvent,
      // Incidental request fields must not enter the delivered event payload.
      ...{
        input: 'private learner answer',
        variables: { name: 'private variable value' },
        mdflow: 'private course prompt',
        debug_session_id: 'private-debug-session',
        title: 'private lesson title',
        error: 'private provider error',
        url: 'https://example.test/private?token=secret',
      },
    });

    expect(trackEvent.mock.calls).toEqual([
      [
        `${answerEdit ? 'teacher_debug_answer_edit' : 'teacher_debug_regenerate'}_start`,
        { shifu_bid: 'course-id', outline_bid: 'lesson-id' },
      ],
    ]);
    finish?.('success');
    finish?.('failed');
    finish?.('cancelled');

    expect(trackEvent.mock.calls).toEqual([
      [
        `${answerEdit ? 'teacher_debug_answer_edit' : 'teacher_debug_regenerate'}_start`,
        { shifu_bid: 'course-id', outline_bid: 'lesson-id' },
      ],
      [
        `${answerEdit ? 'teacher_debug_answer_edit' : 'teacher_debug_regenerate'}_result`,
        {
          shifu_bid: 'course-id',
          outline_bid: 'lesson-id',
          result: 'success',
        },
      ],
    ]);
    expect(JSON.stringify(trackEvent.mock.calls)).not.toContain('private');
  });

  it.each([undefined, ''])(
    'excludes unanchored runs, answers and full restarts (%s)',
    anchor => {
      const trackEvent = jest.fn();
      expect(
        startDebugRegenerateTracking({ ...context, anchor, trackEvent }),
      ).toBeUndefined();
      expect(trackEvent).not.toHaveBeenCalled();
    },
  );

  it.each(['success', 'failed', 'cancelled'] as const)(
    'reports the first terminal outcome %s once',
    result => {
      const trackEvent = jest.fn();
      const finish = startDebugRegenerateTracking({ ...context, trackEvent });
      finish?.(result);
      finish?.('success');
      expect(trackEvent).toHaveBeenCalledTimes(2);
      expect(trackEvent).toHaveBeenLastCalledWith(
        `${answerEdit ? 'teacher_debug_answer_edit' : 'teacher_debug_regenerate'}_result`,
        { shifu_bid: 'course-id', outline_bid: 'lesson-id', result },
      );
    },
  );

  it('counts later deliberate regenerations as separate attempts', () => {
    const trackEvent = jest.fn();
    const first = startDebugRegenerateTracking({ ...context, trackEvent });
    first?.('cancelled');
    const second = startDebugRegenerateTracking({ ...context, trackEvent });
    second?.('success');
    first?.('failed');
    expect(trackEvent.mock.calls.map(([name]) => name)).toEqual([
      `${answerEdit ? 'teacher_debug_answer_edit' : 'teacher_debug_regenerate'}_start`,
      `${answerEdit ? 'teacher_debug_answer_edit' : 'teacher_debug_regenerate'}_result`,
      `${answerEdit ? 'teacher_debug_answer_edit' : 'teacher_debug_regenerate'}_start`,
      `${answerEdit ? 'teacher_debug_answer_edit' : 'teacher_debug_regenerate'}_result`,
    ]);
    expect(trackEvent.mock.calls[1][1].result).toBe('cancelled');
    expect(trackEvent.mock.calls[3][1].result).toBe('success');
  });

  it.each(['sync', 'async'])(
    'does not propagate %s tracking failure or permit a second terminal result',
    async kind => {
      const trackEvent = jest.fn(() => {
        if (kind === 'sync') throw new Error('Tracking failed');
        return Promise.reject(new Error('Tracking failed'));
      });
      const finish = startDebugRegenerateTracking({ ...context, trackEvent });
      expect(() => finish?.('failed')).not.toThrow();
      expect(() => finish?.('success')).not.toThrow();
      await Promise.resolve();
      expect(trackEvent).toHaveBeenCalledTimes(2);
    },
  );
});
