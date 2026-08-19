import {
  consumeStripeCheckoutSession,
  rememberStripeCheckoutSession,
} from '../stripe-storage';

describe('stripe checkout session storage', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('remembers and consumes a checkout marker without exposing order ids', () => {
    rememberStripeCheckoutSession('sess_123');
    expect(sessionStorage.getItem('stripeCheckout:sess_123')).toBe('1');
    expect(consumeStripeCheckoutSession('sess_123')).toBeNull();
    expect(sessionStorage.getItem('stripeCheckout:sess_123')).toBeNull();
    expect(consumeStripeCheckoutSession('sess_123')).toBeNull();
  });

  it('returns null when missing', () => {
    expect(consumeStripeCheckoutSession('unknown')).toBeNull();
  });
});
