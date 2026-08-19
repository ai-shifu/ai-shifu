const checkoutKey = (sessionId: string) => `stripeCheckout:${sessionId}`;
const CHECKOUT_STARTED_VALUE = '1';

export function rememberStripeCheckoutSession(sessionId: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    sessionStorage.setItem(checkoutKey(sessionId), CHECKOUT_STARTED_VALUE);
  } catch {
    // ignore storage errors
  }
}

export function consumeStripeCheckoutSession(sessionId: string): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const key = checkoutKey(sessionId);
    const value = sessionStorage.getItem(key);
    if (value) {
      sessionStorage.removeItem(key);
    }
    return null;
  } catch {
    return null;
  }
}
