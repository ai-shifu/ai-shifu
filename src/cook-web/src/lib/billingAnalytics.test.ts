import {
  buildCreatorBillingAttemptAnalytics,
  buildCreatorBillingResultAnalytics,
  buildCreatorBillingStatusAnalytics,
  resolveCreatorBillingSyncObservation,
  trackCreatorBillingEventSafely,
} from './billingAnalytics';

describe('billingAnalytics', () => {
  test('builds an allowlisted attempt payload without localized or provider response fields', () => {
    const input = {
      billingMarket: 'global' as const,
      productType: 'plan' as const,
      productBid: 'product-bid-1',
      productCode: 'creator-global-growth-yearly',
      billingInterval: 'year',
      priceAmount: 219900,
      currency: 'usd',
      creditAmount: 50000,
      paymentProvider: 'stripe',
      checkoutAction: 'subscribe' as const,
      sourceSurface: 'global_pricing' as const,
      sourceTab: 'plans' as const,
      plan_name: 'Localized Growth Plan',
      display_name: 'Localized Growth Plan',
      redirect_url: 'https://checkout.example.test/secret',
      raw_error: 'card declined for person@example.test',
    };

    expect(buildCreatorBillingAttemptAnalytics(input)).toEqual({
      billing_market: 'global',
      product_type: 'plan',
      product_bid: 'product-bid-1',
      product_code: 'creator-global-growth-yearly',
      billing_interval: 'year',
      price_amount: 219900,
      currency: 'USD',
      credit_amount: 50000,
      payment_provider: 'stripe',
      checkout_action: 'subscribe',
      source_surface: 'global_pricing',
      source_tab: 'plans',
    });
  });

  test('normalizes unbounded provider, currency, interval, and channel values', () => {
    expect(
      buildCreatorBillingStatusAnalytics({
        billingInterval: 'custom interval',
        currency: 'btc',
        paymentProvider: 'custom-provider',
        paymentChannel: 'user-authored-channel',
        sourceSurface: 'billing_overview',
        status: 'pending',
      }),
    ).toEqual({
      billing_interval: 'unknown',
      currency: 'other',
      payment_provider: 'other',
      payment_channel: 'not_applicable',
      source_surface: 'billing_overview',
      status: 'pending',
    });
  });

  test('adds only bounded terminal outcome metadata', () => {
    expect(
      buildCreatorBillingResultAnalytics({
        billOrderBid: 'billing-order-1',
        paymentProvider: 'stripe',
        sourceSurface: 'stripe_return',
        outcome: 'failed',
        failureCategory: 'payment_failed',
      }),
    ).toEqual({
      payment_provider: 'stripe',
      source_surface: 'stripe_return',
      bill_order_bid: 'billing-order-1',
      outcome: 'failed',
      failure_category: 'payment_failed',
    });
  });

  test('keeps a failed confirmation request non-terminal', () => {
    expect(
      buildCreatorBillingStatusAnalytics({
        billOrderBid: 'billing-order-1',
        paymentProvider: 'stripe',
        sourceSurface: 'stripe_return',
        status: 'confirmation_failed',
      }),
    ).toEqual({
      payment_provider: 'stripe',
      source_surface: 'stripe_return',
      bill_order_bid: 'billing-order-1',
      status: 'confirmation_failed',
    });
  });

  test('classifies only paid and refunded billing sync states as terminal', () => {
    expect(resolveCreatorBillingSyncObservation('paid')).toEqual({
      event: 'result',
      outcome: 'success',
    });
    expect(resolveCreatorBillingSyncObservation('refunded')).toEqual({
      event: 'result',
      outcome: 'failed',
      failureCategory: 'payment_failed',
    });
    expect(resolveCreatorBillingSyncObservation('pending')).toEqual({
      event: 'status',
      status: 'pending',
    });
    for (const status of [
      'init',
      'failed',
      'canceled',
      'timeout',
      'private-provider-state',
    ]) {
      expect(resolveCreatorBillingSyncObservation(status)).toEqual({
        event: 'status',
        status: 'confirmation_failed',
      });
    }
  });

  test('swallows synchronous throws and asynchronous rejections from tracking', async () => {
    expect(() =>
      trackCreatorBillingEventSafely(
        () => {
          throw new Error('tracking unavailable');
        },
        'creator_billing_checkout_attempt',
        { source_surface: 'billing_overview' },
      ),
    ).not.toThrow();

    trackCreatorBillingEventSafely(
      () => Promise.reject(new Error('tracking unavailable')),
      'creator_billing_checkout_status',
      { source_surface: 'billing_overview', status: 'pending' },
    );
    await Promise.resolve();
  });
});
