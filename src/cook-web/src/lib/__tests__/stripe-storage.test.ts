import {
  consumeStripeBillingOrderForAnalytics,
  consumeStripeCheckoutSession,
  rememberStripeBillingOrderForAnalytics,
  rememberStripeCheckoutSession,
} from '../stripe-storage';

describe('stripe checkout session storage', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('remembers and consumes order id', () => {
    rememberStripeCheckoutSession('sess_123', 'order_abc');
    expect(consumeStripeCheckoutSession('sess_123')).toBe('order_abc');
    expect(consumeStripeCheckoutSession('sess_123')).toBeNull();
  });

  it('returns null when missing', () => {
    expect(consumeStripeCheckoutSession('unknown')).toBeNull();
  });

  it('remembers a confirmed Stripe billing order for one return', () => {
    rememberStripeBillingOrderForAnalytics('billing_order_123');

    expect(consumeStripeBillingOrderForAnalytics('billing_order_123')).toBe(
      true,
    );
    expect(consumeStripeBillingOrderForAnalytics('billing_order_123')).toBe(
      false,
    );
  });

  it('fails closed when analytics correlation storage is unavailable', () => {
    const setItemSpy = jest
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new Error('storage unavailable');
      });

    expect(() =>
      rememberStripeBillingOrderForAnalytics('billing_order_failed'),
    ).not.toThrow();
    setItemSpy.mockRestore();

    const getItemSpy = jest
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('storage unavailable');
      });

    expect(consumeStripeBillingOrderForAnalytics('billing_order_failed')).toBe(
      false,
    );
    getItemSpy.mockRestore();

    rememberStripeBillingOrderForAnalytics('billing_order_remove_failed');
    const removeItemSpy = jest
      .spyOn(Storage.prototype, 'removeItem')
      .mockImplementation(() => {
        throw new Error('storage unavailable');
      });

    expect(
      consumeStripeBillingOrderForAnalytics('billing_order_remove_failed'),
    ).toBe(false);
    removeItemSpy.mockRestore();
  });
});
