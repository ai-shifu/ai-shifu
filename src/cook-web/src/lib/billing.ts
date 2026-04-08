import type {
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

export function formatBillingPlanInterval(
  t: BillingTranslator,
  product: BillingPlan,
): string {
  if (product.billing_interval === 'year') {
    return t('module.billing.catalog.labels.perYear');
  }
  return t('module.billing.catalog.labels.perMonth');
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
