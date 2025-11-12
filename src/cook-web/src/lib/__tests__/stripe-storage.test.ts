import {
  consumeStripeCheckoutSession,
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
});
