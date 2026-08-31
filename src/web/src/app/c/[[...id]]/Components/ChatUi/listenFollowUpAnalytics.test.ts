import {
  buildListenFollowUpAttemptAnalytics,
  buildListenFollowUpResultAnalytics,
  LISTEN_FOLLOW_UP_ATTEMPT_EVENT,
  LISTEN_FOLLOW_UP_RESULT_EVENT,
} from './listenFollowUpAnalytics';

describe('listen follow-up analytics contract', () => {
  it('uses stable event names and the exact attempt allowlist', () => {
    expect(LISTEN_FOLLOW_UP_ATTEMPT_EVENT).toBe(
      'learner_listen_follow_up_attempt',
    );
    expect(
      buildListenFollowUpAttemptAnalytics({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        surface: 'mobile_fullscreen',
      }),
    ).toEqual({
      shifu_bid: 'shifu-1',
      outline_bid: 'lesson-1',
      surface: 'mobile_fullscreen',
    });
  });

  it.each(['success', 'failed', 'cancelled'] as const)(
    'uses the exact terminal result allowlist for %s',
    outcome => {
      expect(LISTEN_FOLLOW_UP_RESULT_EVENT).toBe(
        'learner_listen_follow_up_result',
      );
      const payload = buildListenFollowUpResultAnalytics({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        surface: 'desktop',
        outcome,
      });

      expect(payload).toEqual({
        shifu_bid: 'shifu-1',
        outline_bid: 'lesson-1',
        surface: 'desktop',
        outcome,
      });
      expect(payload).not.toHaveProperty('question');
      expect(payload).not.toHaveProperty('answer');
      expect(payload).not.toHaveProperty('subtitle');
      expect(payload).not.toHaveProperty('audio_url');
      expect(payload).not.toHaveProperty('error');
      expect(payload).not.toHaveProperty('model');
    },
  );
});
