export const CREATOR_BILLING_ANALYTICS_EVENTS = {
  attempt: 'creator_billing_checkout_attempt',
  result: 'creator_billing_checkout_result',
  status: 'creator_billing_checkout_status',
} as const;

export type CreatorBillingMarket = 'domestic' | 'global';
export type CreatorBillingProductType = 'plan' | 'topup';
export type CreatorBillingInterval =
  | 'day'
  | 'month'
  | 'year'
  | 'one_time'
  | 'unknown';
export type CreatorBillingProvider =
  | 'stripe'
  | 'pingxx'
  | 'alipay'
  | 'wechatpay'
  | 'manual'
  | 'other';
export type CreatorBillingChannel =
  | 'wx_pub_qr'
  | 'alipay_qr'
  | 'not_applicable';
export type CreatorBillingCheckoutAction =
  | 'subscribe'
  | 'upgrade_immediate'
  | 'preorder'
  | 'topup';
export type CreatorBillingSourceSurface =
  | 'global_pricing'
  | 'billing_overview'
  | 'stripe_return';
export type CreatorBillingSourceTab = 'plans' | 'credit_packs' | 'topup';
export type CreatorBillingFailureCategory =
  | 'checkout_request_failed'
  | 'missing_order'
  | 'missing_redirect'
  | 'payment_failed'
  | 'redirect_failed'
  | 'unexpected_status'
  | 'unsupported';

export type CreatorBillingStatus = 'pending' | 'confirmation_failed';

export type CreatorBillingSyncObservation =
  | {
      event: 'result';
      outcome: 'success' | 'failed';
      failureCategory?: CreatorBillingFailureCategory;
    }
  | { event: 'status'; status: CreatorBillingStatus };

export type CreatorBillingAnalyticsBaseInput = {
  billingMarket?: CreatorBillingMarket;
  productType?: CreatorBillingProductType;
  productBid?: string;
  productCode?: string;
  billingInterval?: string;
  priceAmount?: number;
  currency?: string;
  creditAmount?: number;
  paymentProvider?: string;
  paymentChannel?: string;
  checkoutAction?: CreatorBillingCheckoutAction;
  sourceSurface: CreatorBillingSourceSurface;
  sourceTab?: CreatorBillingSourceTab;
  billOrderBid?: string;
};

export type CreatorBillingAnalyticsPayload = Record<string, string | number>;

type CreatorBillingTrackEvent = (
  eventName: string,
  eventData: Record<string, unknown>,
) => unknown;

function optionalStableId(value: string | undefined) {
  const normalized = String(value || '').trim();
  return normalized || undefined;
}

function optionalFiniteNumber(value: number | undefined) {
  return typeof value === 'number' && Number.isFinite(value)
    ? value
    : undefined;
}

export function normalizeCreatorBillingCurrency(currency: string | undefined) {
  const normalized = String(currency || '')
    .trim()
    .toUpperCase();
  if (normalized === 'CNY' || normalized === 'USD') {
    return normalized;
  }
  return 'other';
}

export function normalizeCreatorBillingProvider(
  provider: string | undefined,
): CreatorBillingProvider {
  const normalized = String(provider || '')
    .trim()
    .toLowerCase();
  if (
    normalized === 'stripe' ||
    normalized === 'pingxx' ||
    normalized === 'alipay' ||
    normalized === 'wechatpay' ||
    normalized === 'manual'
  ) {
    return normalized;
  }
  return 'other';
}

export function resolveCreatorBillingSyncObservation(
  status: string,
): CreatorBillingSyncObservation {
  if (status === 'paid') {
    return { event: 'result', outcome: 'success' };
  }
  if (status === 'refunded') {
    return {
      event: 'result',
      outcome: 'failed',
      failureCategory: 'payment_failed',
    };
  }
  if (status === 'pending') {
    return { event: 'status', status: 'pending' };
  }
  return { event: 'status', status: 'confirmation_failed' };
}

function normalizeCreatorBillingChannel(
  channel: string | undefined,
): CreatorBillingChannel {
  if (channel === 'wx_pub_qr' || channel === 'alipay_qr') {
    return channel;
  }
  return 'not_applicable';
}

function normalizeCreatorBillingInterval(
  interval: string | undefined,
): CreatorBillingInterval {
  if (
    interval === 'day' ||
    interval === 'month' ||
    interval === 'year' ||
    interval === 'one_time'
  ) {
    return interval;
  }
  return 'unknown';
}

export function buildCreatorBillingAnalyticsBase({
  billingMarket,
  productType,
  productBid,
  productCode,
  billingInterval,
  priceAmount,
  currency,
  creditAmount,
  paymentProvider,
  paymentChannel,
  checkoutAction,
  sourceSurface,
  sourceTab,
  billOrderBid,
}: CreatorBillingAnalyticsBaseInput): CreatorBillingAnalyticsPayload {
  const safeProductBid = optionalStableId(productBid);
  const safeProductCode = optionalStableId(productCode);
  const safeBillOrderBid = optionalStableId(billOrderBid);
  const safePriceAmount = optionalFiniteNumber(priceAmount);
  const safeCreditAmount = optionalFiniteNumber(creditAmount);

  return {
    ...(billingMarket ? { billing_market: billingMarket } : {}),
    ...(productType ? { product_type: productType } : {}),
    ...(safeProductBid ? { product_bid: safeProductBid } : {}),
    ...(safeProductCode ? { product_code: safeProductCode } : {}),
    ...(billingInterval
      ? { billing_interval: normalizeCreatorBillingInterval(billingInterval) }
      : {}),
    ...(safePriceAmount !== undefined ? { price_amount: safePriceAmount } : {}),
    ...(currency
      ? { currency: normalizeCreatorBillingCurrency(currency) }
      : {}),
    ...(safeCreditAmount !== undefined
      ? { credit_amount: safeCreditAmount }
      : {}),
    ...(paymentProvider
      ? { payment_provider: normalizeCreatorBillingProvider(paymentProvider) }
      : {}),
    ...(paymentChannel
      ? { payment_channel: normalizeCreatorBillingChannel(paymentChannel) }
      : {}),
    ...(checkoutAction ? { checkout_action: checkoutAction } : {}),
    source_surface: sourceSurface,
    ...(sourceTab ? { source_tab: sourceTab } : {}),
    ...(safeBillOrderBid ? { bill_order_bid: safeBillOrderBid } : {}),
  };
}

export function buildCreatorBillingAttemptAnalytics(
  input: CreatorBillingAnalyticsBaseInput,
) {
  return buildCreatorBillingAnalyticsBase(input);
}

export function buildCreatorBillingResultAnalytics(
  input: CreatorBillingAnalyticsBaseInput & {
    outcome: 'success' | 'failed' | 'cancelled';
    failureCategory?: CreatorBillingFailureCategory;
  },
) {
  return {
    ...buildCreatorBillingAnalyticsBase(input),
    outcome: input.outcome,
    ...(input.outcome === 'failed' && input.failureCategory
      ? { failure_category: input.failureCategory }
      : {}),
  };
}

export function buildCreatorBillingStatusAnalytics(
  input: CreatorBillingAnalyticsBaseInput & { status: CreatorBillingStatus },
) {
  return {
    ...buildCreatorBillingAnalyticsBase(input),
    status: input.status,
  };
}

export function trackCreatorBillingEventSafely(
  trackEvent: CreatorBillingTrackEvent,
  eventName: string,
  payload: CreatorBillingAnalyticsPayload,
): void {
  try {
    Promise.resolve(trackEvent(eventName, payload)).catch(() => {});
  } catch {
    // Analytics is best effort and must never alter checkout behavior.
  }
}
