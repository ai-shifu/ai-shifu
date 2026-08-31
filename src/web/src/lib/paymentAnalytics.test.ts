import {
  buildLearnerPaymentAttemptAnalytics,
  buildLearnerPaymentResultAnalytics,
  buildLearnerPaymentStatusAnalytics,
  isSupersededLearnerPaymentAttempt,
  normalizeLearnerPaymentChannel,
  normalizeLearnerPaymentCurrency,
  rememberLearnerProviderConfirmedChannel,
  resolveCurrentLearnerPaymentAttemptChannel,
  resolveLearnerPaymentAttributionChannel,
  resolveLearnerProviderConfirmedChannel,
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

  it('recognizes only a newer same-channel attempt in the current scope', () => {
    const staleAttempt = {
      orderId: 'order-1',
      lifecycle: 3,
      channel: 'stripe' as const,
      attemptId: 7,
    };
    const isSuperseded = (
      orderId: string,
      lifecycle: number,
      attemptedChannels: Array<'stripe' | 'wechat_qr'>,
      activeAttemptId?: number,
    ) =>
      isSupersededLearnerPaymentAttempt(
        staleAttempt,
        orderId,
        lifecycle,
        attemptedChannels,
        activeAttemptId === undefined
          ? new Map()
          : new Map([['stripe' as const, activeAttemptId]]),
      );

    expect(isSuperseded('order-1', 3, ['stripe'], 8)).toBe(true);
    expect(isSuperseded('order-1', 3, ['stripe'], 7)).toBe(false);
    expect(isSuperseded('order-1', 3, ['stripe'], 6)).toBe(false);
    expect(isSuperseded('order-2', 3, ['stripe'], 8)).toBe(false);
    expect(isSuperseded('order-1', 4, ['stripe'], 8)).toBe(false);
    expect(isSuperseded('order-1', 3, ['wechat_qr'], 8)).toBe(false);
    expect(isSuperseded('order-1', 3, ['stripe'])).toBe(false);
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
    expect(resolveLearnerProviderConfirmedChannel([], [])).toBeUndefined();
    expect(resolveLearnerProviderConfirmedChannel(['stripe'], ['stripe'])).toBe(
      'stripe',
    );
    expect(
      resolveLearnerProviderConfirmedChannel(['stripe', 'stripe'], ['stripe']),
    ).toBe('stripe');
    expect(
      resolveLearnerProviderConfirmedChannel(
        ['stripe', 'wechat_jsapi'],
        ['stripe', 'wechat_jsapi'],
      ),
    ).toBeUndefined();
    expect(
      resolveLearnerProviderConfirmedChannel(
        ['stripe'],
        ['wechat_qr', 'alipay_qr'],
      ),
    ).toBeUndefined();
    const stripeAttempt = {
      orderId: 'order-1',
      lifecycle: 3,
      channel: 'stripe' as const,
      attemptId: 7,
    };
    const activeAttemptIds = new Map([['stripe' as const, 7]]);
    expect(
      resolveCurrentLearnerPaymentAttemptChannel(
        stripeAttempt,
        'order-1',
        3,
        ['wechat_qr', 'stripe'],
        activeAttemptIds,
      ),
    ).toBe('stripe');
    expect(
      resolveCurrentLearnerPaymentAttemptChannel(
        stripeAttempt,
        'order-2',
        3,
        ['wechat_qr', 'stripe'],
        activeAttemptIds,
      ),
    ).toBeUndefined();
    expect(
      resolveCurrentLearnerPaymentAttemptChannel(
        stripeAttempt,
        'order-1',
        4,
        ['wechat_qr', 'stripe'],
        activeAttemptIds,
      ),
    ).toBeUndefined();
    expect(
      resolveCurrentLearnerPaymentAttemptChannel(
        stripeAttempt,
        'order-1',
        3,
        ['wechat_qr'],
        activeAttemptIds,
      ),
    ).toBeUndefined();
    expect(
      resolveCurrentLearnerPaymentAttemptChannel(
        stripeAttempt,
        'order-1',
        3,
        ['wechat_qr', 'stripe'],
        new Map([['stripe' as const, 8]]),
      ),
    ).toBeUndefined();
    const evidenceByOrder = new Map();
    expect(
      rememberLearnerProviderConfirmedChannel(
        evidenceByOrder,
        stripeAttempt,
        'order-1',
        3,
        ['wechat_qr', 'stripe'],
        activeAttemptIds,
      ),
    ).toBe(true);
    expect(evidenceByOrder.get('order-1')).toEqual(new Set(['stripe']));
    expect(
      rememberLearnerProviderConfirmedChannel(
        evidenceByOrder,
        stripeAttempt,
        'order-2',
        3,
        ['wechat_qr', 'stripe'],
        activeAttemptIds,
      ),
    ).toBe(false);
    expect(evidenceByOrder.has('order-2')).toBe(false);
    expect(
      rememberLearnerProviderConfirmedChannel(
        evidenceByOrder,
        stripeAttempt,
        'order-1',
        4,
        ['wechat_qr', 'stripe'],
        activeAttemptIds,
      ),
    ).toBe(false);
    expect(
      rememberLearnerProviderConfirmedChannel(
        evidenceByOrder,
        stripeAttempt,
        'order-1',
        3,
        ['wechat_qr'],
        activeAttemptIds,
      ),
    ).toBe(false);
    expect(evidenceByOrder.has('order-2')).toBe(false);
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
