const checkoutKey = (sessionId: string) => `stripeCheckout:${sessionId}`;
const billingAnalyticsKey = (orderId: string) =>
  `stripeBillingAnalytics:${orderId}`;

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

export function rememberStripeBillingOrderForAnalytics(orderId: string): void {
  if (typeof window === 'undefined' || !orderId) {
    return;
  }
  try {
    sessionStorage.setItem(billingAnalyticsKey(orderId), '1');
  } catch {
    // Analytics correlation is best-effort and must not block checkout.
  }
}

export function consumeStripeBillingOrderForAnalytics(
  orderId: string,
): boolean {
  if (typeof window === 'undefined' || !orderId) {
    return false;
  }
  try {
    const key = billingAnalyticsKey(orderId);
    const remembered = sessionStorage.getItem(key) === '1';
    if (remembered) {
      sessionStorage.removeItem(key);
    }
    return remembered;
  } catch {
    return false;
  }
}
