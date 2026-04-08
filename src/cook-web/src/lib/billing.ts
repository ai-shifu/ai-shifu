import type {
  BillingBucketCategory,
  BillingBucketSourceType,
  BillingBucketStatus,
  BillingPlan,
  BillingSubscription,
  BillingSubscriptionStatus,
  BillingTopupProduct,
} from '@/types/billing';

type BillingTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

const BILLING_STATUS_KEYS: Record<string, string> = {
  active: 'module.billing.status.active',
  draft: 'module.billing.status.draft',
  past_due: 'module.billing.status.pastDue',
  paused: 'module.billing.status.paused',
  cancel_scheduled: 'module.billing.status.cancelScheduled',
  canceled: 'module.billing.status.canceled',
  expired: 'module.billing.status.expired',
  none: 'module.billing.status.none',
};

const BILLING_BUCKET_CATEGORY_KEYS: Record<BillingBucketCategory, string> = {
  free: 'module.billing.ledger.category.free',
  subscription: 'module.billing.ledger.category.subscription',
  topup: 'module.billing.ledger.category.topup',
};

const BILLING_BUCKET_SOURCE_KEYS: Record<BillingBucketSourceType, string> = {
  subscription: 'module.billing.ledger.source.subscription',
  topup: 'module.billing.ledger.source.topup',
  gift: 'module.billing.ledger.source.gift',
  refund: 'module.billing.ledger.source.refund',
  manual: 'module.billing.ledger.source.manual',
  usage: 'module.billing.ledger.source.usage',
};

const BILLING_BUCKET_STATUS_KEYS: Record<BillingBucketStatus, string> = {
  active: 'module.billing.ledger.bucketStatus.active',
  exhausted: 'module.billing.ledger.bucketStatus.exhausted',
  expired: 'module.billing.ledger.bucketStatus.expired',
  canceled: 'module.billing.ledger.bucketStatus.canceled',
};

export function formatBillingCredits(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

export function formatBillingPrice(
  amountInMinor: number,
  currency: string,
  locale: string,
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: currency || 'CNY',
    maximumFractionDigits: 2,
  }).format(Number(amountInMinor || 0) / 100);
}

export function resolveBillingSubscriptionStatusLabel(
  t: BillingTranslator,
  status?: BillingSubscriptionStatus | null,
): string {
  const normalizedStatus = String(status || 'none');
  return t(BILLING_STATUS_KEYS[normalizedStatus] || BILLING_STATUS_KEYS.none);
}

export function resolveBillingProductTitle(
  t: BillingTranslator,
  product?: BillingPlan | BillingTopupProduct | null,
  fallback = '',
): string {
  if (!product?.display_name) {
    return fallback;
  }
  return t(product.display_name);
}

export function resolveBillingProductDescription(
  t: BillingTranslator,
  product?: BillingPlan | BillingTopupProduct | null,
  fallback = '',
): string {
  if (!product?.description) {
    return fallback;
  }
  return t(product.description);
}

export function buildBillingStripeResultUrls(origin: string): {
  cancelUrl: string;
  successUrl: string;
} {
  const normalizedOrigin = String(origin || '').replace(/\/+$/, '');
  const base = `${normalizedOrigin}/payment/stripe/billing-result`;
  return {
    successUrl: base,
    cancelUrl: `${base}?canceled=1`,
  };
}

export function resolveBillingNextActionLabel(
  t: BillingTranslator,
  subscription: BillingSubscription | null,
  availableCredits: number,
): string {
  if (!subscription) {
    return t('module.billing.overview.actions.choosePlan');
  }
  if (availableCredits <= 0) {
    return t('module.billing.overview.actions.topupCredits');
  }
  if (subscription.cancel_at_period_end) {
    return t('module.billing.overview.actions.watchRenewal');
  }
  return t('module.billing.overview.actions.managePlan');
}

export function formatBillingDate(
  value: string | null | undefined,
  locale: string,
): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

export function formatBillingDateTime(
  value: string | null | undefined,
  locale: string,
): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatBillingPlanInterval(
  t: BillingTranslator,
  product: BillingPlan,
): string {
  if (product.billing_interval === 'year') {
    return t('module.billing.catalog.labels.perYear');
  }
  return t('module.billing.catalog.labels.perMonth');
}

export function resolveBillingBucketCategoryLabel(
  t: BillingTranslator,
  category: BillingBucketCategory,
): string {
  return t(BILLING_BUCKET_CATEGORY_KEYS[category]);
}

export function resolveBillingBucketSourceLabel(
  t: BillingTranslator,
  sourceType: BillingBucketSourceType,
): string {
  return t(BILLING_BUCKET_SOURCE_KEYS[sourceType]);
}

export function resolveBillingBucketStatusLabel(
  t: BillingTranslator,
  status: BillingBucketStatus,
): string {
  return t(BILLING_BUCKET_STATUS_KEYS[status]);
}

export function openBillingCheckoutUrl(url: string): void {
  if (!url || typeof window === 'undefined') {
    return;
  }
  window.location.assign(url);
}

export function openBillingPaymentWindow(url: string): boolean {
  if (!url || typeof window === 'undefined') {
    return false;
  }
  const paymentWindow = window.open(url, '_blank', 'noopener,noreferrer');
  return paymentWindow !== null;
}

export function registerBillingTranslationUsage(t: BillingTranslator): void {
  void [
    t('module.billing.catalog.badges.bestValue'),
    t('module.billing.catalog.badges.recommended'),
    t('module.billing.catalog.plans.creatorMonthly.description'),
    t('module.billing.catalog.plans.creatorMonthly.title'),
    t('module.billing.catalog.plans.creatorYearly.description'),
    t('module.billing.catalog.plans.creatorYearly.title'),
    t('module.billing.catalog.topups.creatorLarge.description'),
    t('module.billing.catalog.topups.creatorLarge.title'),
    t('module.billing.catalog.topups.creatorSmall.description'),
    t('module.billing.catalog.topups.creatorSmall.title'),
    t('module.billing.checkout.planDescription'),
    t('module.billing.checkout.topupDescription'),
    t('module.billing.ledger.bucketDescription'),
    t('module.billing.ledger.bucketStatus.active'),
    t('module.billing.ledger.bucketStatus.canceled'),
    t('module.billing.ledger.bucketStatus.exhausted'),
    t('module.billing.ledger.bucketStatus.expired'),
    t('module.billing.ledger.category.free'),
    t('module.billing.ledger.category.subscription'),
    t('module.billing.ledger.category.topup'),
    t('module.billing.ledger.entriesDescription'),
    t('module.billing.ledger.entriesTitle'),
    t('module.billing.ledger.empty'),
    t('module.billing.ledger.loadError'),
    t('module.billing.ledger.neverExpires'),
    t('module.billing.ledger.source.gift'),
    t('module.billing.ledger.source.manual'),
    t('module.billing.ledger.source.refund'),
    t('module.billing.ledger.source.subscription'),
    t('module.billing.ledger.source.topup'),
    t('module.billing.ledger.source.usage'),
    t('module.billing.ledger.summary.activeBuckets'),
    t('module.billing.ledger.summary.nextExpiry'),
    t('module.billing.ledger.summary.totalAvailable'),
    t('module.billing.ledger.table.availableCredits'),
    t('module.billing.ledger.table.effectiveWindow'),
    t('module.billing.ledger.table.priority'),
    t('module.billing.ledger.table.source'),
    t('module.billing.ledger.table.status'),
    t('module.billing.status.active'),
    t('module.billing.status.cancelScheduled'),
    t('module.billing.status.canceled'),
    t('module.billing.status.draft'),
    t('module.billing.status.expired'),
    t('module.billing.status.none'),
    t('module.billing.status.pastDue'),
    t('module.billing.status.paused'),
  ];
}
