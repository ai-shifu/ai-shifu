import {
  buildLearnerPaymentAttemptAnalytics,
  buildLearnerPaymentResultAnalytics,
  buildLearnerPaymentStatusAnalytics,
  normalizeLearnerPaymentChannel,
  trackLearnerPaymentEventSafely,
} from './paymentAnalytics';

describe('learner payment analytics', () => {
  it.each([
    ['stripe:checkout_session', 'stripe'],
    ['wx_pub', 'wechat_jsapi'],
    ['wx_pub_qr', 'wechat_qr'],
    ['alipay_qr', 'alipay_qr'],
    ['unknown-provider', 'other'],
  ] as const)('normalizes %s to %s', (input, expected) => {
    expect(normalizeLearnerPaymentChannel(input)).toBe(expected);
  });

  it('builds flat attempt and result payloads without payment secrets', () => {
    const input = {
      shifuBid: 'course-1',
      orderId: 'order-1',
      channel: 'stripe' as const,
      surface: 'desktop' as const,
    };
    expect(buildLearnerPaymentAttemptAnalytics(input)).toEqual({
      shifu_bid: 'course-1',
      order_id: 'order-1',
      channel: 'stripe',
      surface: 'desktop',
    });
    expect(
      buildLearnerPaymentResultAnalytics({
        ...input,
        outcome: 'failed',
        failureCategory: 'provider_failed',
      }),
    ).toEqual({
      shifu_bid: 'course-1',
      order_id: 'order-1',
      channel: 'stripe',
      surface: 'desktop',
      outcome: 'failed',
      failure_category: 'provider_failed',
    });
    expect(
      buildLearnerPaymentStatusAnalytics({ ...input, status: 'pending' }),
    ).toEqual({
      shifu_bid: 'course-1',
      order_id: 'order-1',
      channel: 'stripe',
      surface: 'desktop',
      status: 'pending',
    });
  });

  it('keeps learner payment behavior fail-open when tracking fails', async () => {
    expect(() =>
      trackLearnerPaymentEventSafely(
        () => {
          throw new Error('tracking unavailable');
        },
        'learner_payment_attempt',
        { channel: 'stripe', surface: 'desktop' },
      ),
    ).not.toThrow();

    trackLearnerPaymentEventSafely(
      () => Promise.reject(new Error('tracking unavailable')),
      'learner_payment_result',
      { channel: 'stripe', surface: 'desktop', outcome: 'failed' },
    );
    await Promise.resolve();
  });
});
