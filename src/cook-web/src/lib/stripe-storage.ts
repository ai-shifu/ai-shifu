const checkoutKey = (sessionId: string) => `stripeCheckout:${sessionId}`;

export function rememberStripeCheckoutSession(
  sessionId: string,
  orderId: string,
): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    sessionStorage.setItem(checkoutKey(sessionId), orderId);
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
    return value;
  } catch {
    return null;
  }
}
