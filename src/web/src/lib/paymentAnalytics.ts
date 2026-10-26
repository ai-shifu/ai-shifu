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

export interface LearnerPaymentAttemptContext {
  readonly orderId: string;
  readonly lifecycle: number;
  readonly channel: LearnerPaymentChannel;
  readonly attemptId: number;
}

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

export const isSupersededLearnerPaymentAttempt = (
  attempt: LearnerPaymentAttemptContext | undefined,
  currentOrderId: string,
  currentLifecycle: number,
  attemptedChannels: Iterable<LearnerPaymentChannel>,
  activeAttemptIds: ReadonlyMap<LearnerPaymentChannel, number>,
): boolean => {
  if (
    !attempt?.orderId ||
    attempt.orderId !== currentOrderId ||
    attempt.lifecycle !== currentLifecycle ||
    !new Set(attemptedChannels).has(attempt.channel)
  ) {
    return false;
  }
  const activeAttemptId = activeAttemptIds.get(attempt.channel);
  return activeAttemptId !== undefined && activeAttemptId > attempt.attemptId;
};

export const resolveLearnerPaymentAttributionChannel = (
  channels: Iterable<LearnerPaymentChannel>,
  confirmedChannel?: LearnerPaymentChannel,
): LearnerPaymentChannel | null => {
  const distinctChannels = new Set(channels);
  if (distinctChannels.size === 0) return null;
  if (confirmedChannel) {
    return distinctChannels.has(confirmedChannel) ? confirmedChannel : null;
  }
  if (distinctChannels.size > 1) return 'other';
  return distinctChannels.values().next().value ?? null;
};

export const resolveCurrentLearnerPaymentAttemptChannel = (
  attempt: LearnerPaymentAttemptContext | undefined,
  currentOrderId: string,
  currentLifecycle: number,
  attemptedChannels: Iterable<LearnerPaymentChannel>,
  activeAttemptIds: ReadonlyMap<LearnerPaymentChannel, number>,
): LearnerPaymentChannel | undefined => {
  if (
    !attempt?.orderId ||
    attempt.orderId !== currentOrderId ||
    attempt.lifecycle !== currentLifecycle ||
    activeAttemptIds.get(attempt.channel) !== attempt.attemptId
  ) {
    return undefined;
  }
  return new Set(attemptedChannels).has(attempt.channel)
    ? attempt.channel
    : undefined;
};

export const rememberLearnerProviderConfirmedChannel = (
  evidenceByOrder: Map<string, Set<LearnerPaymentChannel>>,
  attempt: LearnerPaymentAttemptContext | undefined,
  currentOrderId: string,
  currentLifecycle: number,
  attemptedChannels: Iterable<LearnerPaymentChannel>,
  activeAttemptIds: ReadonlyMap<LearnerPaymentChannel, number>,
): boolean => {
  const channel = resolveCurrentLearnerPaymentAttemptChannel(
    attempt,
    currentOrderId,
    currentLifecycle,
    attemptedChannels,
    activeAttemptIds,
  );
  if (!channel || !attempt) return false;
  const confirmedChannels =
    evidenceByOrder.get(attempt.orderId) || new Set<LearnerPaymentChannel>();
  confirmedChannels.add(channel);
  evidenceByOrder.set(attempt.orderId, confirmedChannels);
  return true;
};

export const resolveLearnerProviderConfirmedChannel = (
  confirmedChannels: Iterable<LearnerPaymentChannel>,
  unresolvedChannels: Iterable<LearnerPaymentChannel>,
): LearnerPaymentChannel | undefined => {
  const unresolved = new Set(unresolvedChannels);
  const eligibleChannels = new Set(
    Array.from(confirmedChannels).filter(channel => unresolved.has(channel)),
  );
  if (eligibleChannels.size !== 1) return undefined;
  return eligibleChannels.values().next().value;
};

export const normalizeLearnerPaymentCurrency = (
  currency: string | undefined,
) => {
  const normalized = String(currency || '')
    .trim()
    .toUpperCase();
  if (normalized === 'CNY' || normalized === 'USD') {
    return normalized;
  }
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
