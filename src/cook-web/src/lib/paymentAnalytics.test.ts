import {
  buildLearnerPaymentAttemptAnalytics,
  buildLearnerPaymentResultAnalytics,
  buildLearnerPaymentStatusAnalytics,
  normalizeLearnerPaymentChannel,
  normalizeLearnerPaymentCurrency,
  resolveLearnerPaymentAttributionChannel,
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

  it('uses other for multiple unresolved attempted channels', () => {
    expect(resolveLearnerPaymentAttributionChannel([])).toBeNull();
    expect(
      resolveLearnerPaymentAttributionChannel(['wechat_qr', 'wechat_qr']),
    ).toBe('wechat_qr');
    expect(
      resolveLearnerPaymentAttributionChannel(['wechat_qr', 'alipay_qr']),
    ).toBe('other');
    expect(
      resolveLearnerPaymentAttributionChannel(
        ['wechat_qr', 'alipay_qr'],
        'wechat_qr',
      ),
    ).toBe('wechat_qr');
    expect(resolveLearnerPaymentAttributionChannel([], 'stripe')).toBeNull();
    expect(
      resolveLearnerPaymentAttributionChannel(['wechat_qr'], 'stripe'),
    ).toBeNull();
  });

  it.each([
    ['cny', 'CNY'],
    ['USD', 'USD'],
    ['custom-person@example.test', 'other'],
    ['', 'other'],
  ] as const)('normalizes currency %s to %s', (input, expected) => {
    expect(normalizeLearnerPaymentCurrency(input)).toBe(expected);
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
