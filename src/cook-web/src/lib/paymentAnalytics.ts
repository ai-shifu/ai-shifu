export type LearnerPaymentChannel =
  | 'wechat_jsapi'
  | 'wechat_qr'
  | 'alipay_qr'
  | 'stripe'
  | 'other';
export type LearnerPaymentSurface = 'desktop' | 'mobile' | 'stripe_return';
export type LearnerPaymentFailureCategory =
  | 'provider_failed'
  | 'missing_order'
  | 'status_lookup_failed';

type LearnerPaymentTrackEvent = (
  eventName: string,
  eventData: Record<string, unknown>,
) => unknown;

export const normalizeLearnerPaymentChannel = (
  channel: string | undefined,
): LearnerPaymentChannel => {
  const normalized = String(channel || '')
    .trim()
    .toLowerCase();
  if (normalized.startsWith('stripe')) return 'stripe';
  if (normalized === 'wx_pub') return 'wechat_jsapi';
  if (normalized === 'wx_pub_qr') return 'wechat_qr';
  if (normalized === 'alipay_qr') return 'alipay_qr';
  return 'other';
};

type LearnerPaymentBase = {
  shifuBid?: string;
  orderId?: string;
  channel: LearnerPaymentChannel;
  surface: LearnerPaymentSurface;
};

const buildLearnerPaymentBase = ({
  shifuBid,
  orderId,
  channel,
  surface,
}: LearnerPaymentBase) => ({
  ...(shifuBid ? { shifu_bid: shifuBid } : {}),
  ...(orderId ? { order_id: orderId } : {}),
  channel,
  surface,
});

export const buildLearnerPaymentAttemptAnalytics = (
  input: LearnerPaymentBase,
) => buildLearnerPaymentBase(input);

export const buildLearnerPaymentResultAnalytics = (
  input: LearnerPaymentBase & {
    outcome: 'success' | 'failed' | 'cancelled';
    failureCategory?: LearnerPaymentFailureCategory;
  },
) => ({
  ...buildLearnerPaymentBase(input),
  outcome: input.outcome,
  ...(input.outcome === 'failed' && input.failureCategory
    ? { failure_category: input.failureCategory }
    : {}),
});

export const buildLearnerPaymentStatusAnalytics = (
  input: LearnerPaymentBase & { status: 'pending' },
) => ({
  ...buildLearnerPaymentBase(input),
  status: input.status,
});

export const trackLearnerPaymentEventSafely = (
  trackEvent: LearnerPaymentTrackEvent,
  eventName: string,
  eventData: Record<string, unknown>,
): void => {
  try {
    Promise.resolve(trackEvent(eventName, eventData)).catch(() => {});
  } catch {
    // Product analytics is best effort and must never alter payment behavior.
  }
};
