import type { Stripe } from '@stripe/stripe-js';
import { loadStripe } from '@stripe/stripe-js';

let cachedKey: string | null = null;
let stripePromise: Promise<Stripe | null> | null = null;

/**
 * Load a singleton Stripe instance on the client.
 */
export async function getStripeInstance(
  publishableKey: string,
): Promise<Stripe | null> {
  if (typeof window === 'undefined') {
    return null;
  }

  if (!publishableKey) {
    return null;
  }

  if (!stripePromise || !cachedKey || cachedKey !== publishableKey) {
    cachedKey = publishableKey;
    stripePromise = loadStripe(publishableKey);
  }

  return stripePromise;
}
