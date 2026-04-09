import type {
  BillingBucketCategory,
  BillingBucketSourceType,
  BillingBucketStatus,
  BillingLedgerEntryType,
  BillingMetricName,
  BillingPaymentMode,
  BillingOrderStatus,
  BillingOrderType,
  BillingPlan,
  BillingProvider,
  BillingRenewalEventStatus,
  BillingRenewalEventSummary,
  BillingRenewalEventType,
  BillingSubscription,
  BillingSubscriptionStatus,
  BillingTopupProduct,
  BillingUsageScene,
  BillingUsageType,
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

const BILLING_LEDGER_ENTRY_KEYS: Record<BillingLedgerEntryType, string> = {
  grant: 'module.billing.ledger.entryType.grant',
  consume: 'module.billing.ledger.entryType.consume',
  refund: 'module.billing.ledger.entryType.refund',
  expire: 'module.billing.ledger.entryType.expire',
  adjustment: 'module.billing.ledger.entryType.adjustment',
  hold: 'module.billing.ledger.entryType.hold',
  release: 'module.billing.ledger.entryType.release',
};

const BILLING_USAGE_SCENE_KEYS: Record<BillingUsageScene, string> = {
  debug: 'module.billing.ledger.usageScene.debug',
  preview: 'module.billing.ledger.usageScene.preview',
  production: 'module.billing.ledger.usageScene.production',
};

const BILLING_ORDER_STATUS_KEYS: Record<BillingOrderStatus, string> = {
  init: 'module.billing.orders.status.init',
  pending: 'module.billing.orders.status.pending',
  paid: 'module.billing.orders.status.paid',
  failed: 'module.billing.orders.status.failed',
  refunded: 'module.billing.orders.status.refunded',
  canceled: 'module.billing.orders.status.canceled',
  timeout: 'module.billing.orders.status.timeout',
};

const BILLING_ORDER_TYPE_KEYS: Record<BillingOrderType, string> = {
  subscription_start: 'module.billing.orders.type.subscriptionStart',
  subscription_upgrade: 'module.billing.orders.type.subscriptionUpgrade',
  subscription_renewal: 'module.billing.orders.type.subscriptionRenewal',
  topup: 'module.billing.orders.type.topup',
  manual: 'module.billing.orders.type.manual',
  refund: 'module.billing.orders.type.refund',
};

const BILLING_PROVIDER_KEYS: Record<BillingProvider, string> = {
  stripe: 'module.billing.catalog.labels.providerStripe',
  pingxx: 'module.billing.catalog.labels.providerPingxx',
};

const BILLING_PAYMENT_MODE_KEYS: Record<BillingPaymentMode, string> = {
  subscription: 'module.billing.orders.paymentMode.subscription',
  one_time: 'module.billing.orders.paymentMode.oneTime',
};

const BILLING_RENEWAL_EVENT_TYPE_KEYS: Record<BillingRenewalEventType, string> =
  {
    renewal: 'module.billing.renewal.eventType.renewal',
    retry: 'module.billing.renewal.eventType.retry',
    cancel_effective: 'module.billing.renewal.eventType.cancelEffective',
    downgrade_effective: 'module.billing.renewal.eventType.downgradeEffective',
    expire: 'module.billing.renewal.eventType.expire',
    reconcile: 'module.billing.renewal.eventType.reconcile',
  };

const BILLING_RENEWAL_EVENT_STATUS_KEYS: Record<
  BillingRenewalEventStatus,
  string
> = {
  pending: 'module.billing.renewal.status.pending',
  processing: 'module.billing.renewal.status.processing',
  succeeded: 'module.billing.renewal.status.succeeded',
  failed: 'module.billing.renewal.status.failed',
  canceled: 'module.billing.renewal.status.canceled',
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

export function resolveBillingLedgerEntryLabel(
  t: BillingTranslator,
  entryType: BillingLedgerEntryType,
): string {
  return t(BILLING_LEDGER_ENTRY_KEYS[entryType]);
}

export function resolveBillingUsageSceneLabel(
  t: BillingTranslator,
  scene?: BillingUsageScene | null,
): string {
  if (!scene) {
    return '';
  }
  return t(BILLING_USAGE_SCENE_KEYS[scene]);
}

export function resolveBillingUsageTypeLabel(
  t: BillingTranslator,
  usageType: BillingUsageType,
): string {
  switch (usageType) {
    case 'tts':
      return t('module.billing.reports.usageType.tts');
    default:
      return t('module.billing.reports.usageType.llm');
  }
}

export function resolveBillingMetricLabel(
  t: BillingTranslator,
  metric: BillingMetricName,
): string {
  switch (metric) {
    case 'llm_input_tokens':
      return t('module.billing.reports.metric.llmInputTokens');
    case 'llm_cache_tokens':
      return t('module.billing.reports.metric.llmCacheTokens');
    case 'tts_request_count':
      return t('module.billing.reports.metric.ttsRequestCount');
    case 'tts_output_chars':
      return t('module.billing.reports.metric.ttsOutputChars');
    case 'tts_input_chars':
      return t('module.billing.reports.metric.ttsInputChars');
    default:
      return t('module.billing.reports.metric.llmOutputTokens');
  }
}

export function resolveBillingOrderStatusLabel(
  t: BillingTranslator,
  status: BillingOrderStatus,
): string {
  return t(BILLING_ORDER_STATUS_KEYS[status]);
}

export function resolveBillingOrderTypeLabel(
  t: BillingTranslator,
  orderType: BillingOrderType,
): string {
  return t(BILLING_ORDER_TYPE_KEYS[orderType]);
}

export function resolveBillingProviderLabel(
  t: BillingTranslator,
  provider: BillingProvider,
): string {
  return t(BILLING_PROVIDER_KEYS[provider]);
}

export function resolveBillingPaymentModeLabel(
  t: BillingTranslator,
  paymentMode: BillingPaymentMode,
): string {
  return t(BILLING_PAYMENT_MODE_KEYS[paymentMode]);
}

export function resolveBillingRenewalEventTypeLabel(
  t: BillingTranslator,
  eventType: BillingRenewalEventType,
): string {
  return t(BILLING_RENEWAL_EVENT_TYPE_KEYS[eventType]);
}

export function resolveBillingRenewalEventStatusLabel(
  t: BillingTranslator,
  status: BillingRenewalEventStatus,
): string {
  return t(BILLING_RENEWAL_EVENT_STATUS_KEYS[status]);
}

export function resolveBillingEmptyLabel(t: BillingTranslator): string {
  return t('module.billing.common.empty');
}

export function buildBillingRenewalContextLabel(
  t: BillingTranslator,
  locale: string,
  event: BillingRenewalEventSummary | null | undefined,
): string {
  if (!event) {
    return resolveBillingEmptyLabel(t);
  }

  const prefix = `${resolveBillingRenewalEventTypeLabel(t, event.event_type)} · ${resolveBillingRenewalEventStatusLabel(t, event.status)}`;
  if (event.last_error) {
    return `${prefix} · ${event.last_error}`;
  }
  if (event.scheduled_at) {
    return `${prefix} · ${t('module.billing.admin.subscriptions.table.scheduled')} ${formatBillingDateTime(event.scheduled_at, locale)}`;
  }
  if (event.processed_at) {
    return `${prefix} · ${formatBillingDateTime(event.processed_at, locale)}`;
  }
  return prefix;
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
    t('module.billing.alerts.actions.checkoutTopup'),
    t('module.billing.alerts.actions.openOrders'),
    t('module.billing.alerts.actions.resumeSubscription'),
    t('module.billing.alerts.cancelScheduled'),
    t('module.billing.alerts.lowBalance'),
    t('module.billing.alerts.subscriptionPastDue'),
    t('module.billing.checkout.planDescription'),
    t('module.billing.checkout.topupDescription'),
    t('module.billing.domains.actions.bind'),
    t('module.billing.domains.actions.binding'),
    t('module.billing.domains.actions.disable'),
    t('module.billing.domains.actions.disabling'),
    t('module.billing.domains.actions.loadError'),
    t('module.billing.domains.actions.verify'),
    t('module.billing.domains.actions.verifying'),
    t('module.billing.domains.branding.description'),
    t('module.billing.domains.branding.disabled'),
    t('module.billing.domains.branding.enabled'),
    t('module.billing.domains.branding.fields.favicon'),
    t('module.billing.domains.branding.fields.homeUrl'),
    t('module.billing.domains.branding.fields.logoSquare'),
    t('module.billing.domains.branding.fields.logoWide'),
    t('module.billing.domains.branding.runtimeNote'),
    t('module.billing.domains.branding.title'),
    t('module.billing.domains.description'),
    t('module.billing.domains.feedback.bind'),
    t('module.billing.domains.feedback.disable'),
    t('module.billing.domains.feedback.verify'),
    t('module.billing.domains.form.capabilityBlocked'),
    t('module.billing.domains.form.errors.hostRequired'),
    t('module.billing.domains.form.hostHelp'),
    t('module.billing.domains.form.hostLabel'),
    t('module.billing.domains.form.hostPlaceholder'),
    t('module.billing.domains.records.description'),
    t('module.billing.domains.records.effective'),
    t('module.billing.domains.records.empty'),
    t('module.billing.domains.records.fields.lastVerified'),
    t('module.billing.domains.records.fields.method'),
    t('module.billing.domains.records.fields.recordName'),
    t('module.billing.domains.records.fields.recordValue'),
    t('module.billing.domains.records.neverVerified'),
    t('module.billing.domains.records.title'),
    t('module.billing.domains.records.verificationError'),
    t('module.billing.domains.settings.description'),
    t('module.billing.domains.settings.disabled'),
    t('module.billing.domains.settings.effectiveDomain'),
    t('module.billing.domains.settings.enabled'),
    t('module.billing.domains.settings.noEffectiveDomain'),
    t('module.billing.domains.settings.title'),
    t('module.billing.domains.ssl.issued'),
    t('module.billing.domains.ssl.not_requested'),
    t('module.billing.domains.ssl.pending'),
    t('module.billing.domains.status.disabled'),
    t('module.billing.domains.status.failed'),
    t('module.billing.domains.status.pending'),
    t('module.billing.domains.status.verified'),
    t('module.billing.domains.title'),
    t('module.billing.domains.verificationMethod.dns_txt'),
    t('module.billing.entitlements.analytics.advanced'),
    t('module.billing.entitlements.analytics.basic'),
    t('module.billing.entitlements.analytics.enterprise'),
    t('module.billing.entitlements.description'),
    t('module.billing.entitlements.flags.branding'),
    t('module.billing.entitlements.flags.brandingDescription'),
    t('module.billing.entitlements.flags.customDomain'),
    t('module.billing.entitlements.flags.customDomainDescription'),
    t('module.billing.entitlements.flags.description'),
    t('module.billing.entitlements.flags.disabled'),
    t('module.billing.entitlements.flags.enabled'),
    t('module.billing.entitlements.flags.title'),
    t('module.billing.entitlements.loadError'),
    t('module.billing.entitlements.metricDescriptions.analyticsTier'),
    t('module.billing.entitlements.metricDescriptions.maxConcurrency'),
    t('module.billing.entitlements.metricDescriptions.priorityClass'),
    t('module.billing.entitlements.metricDescriptions.supportTier'),
    t('module.billing.entitlements.metrics.analyticsTier'),
    t('module.billing.entitlements.metrics.maxConcurrency'),
    t('module.billing.entitlements.metrics.priorityClass'),
    t('module.billing.entitlements.metrics.supportTier'),
    t('module.billing.entitlements.priority.priority'),
    t('module.billing.entitlements.priority.standard'),
    t('module.billing.entitlements.priority.vip'),
    t('module.billing.entitlements.runtimeBadge'),
    t('module.billing.entitlements.runtimeNote'),
    t('module.billing.entitlements.support.businessHours'),
    t('module.billing.entitlements.support.priority'),
    t('module.billing.entitlements.support.selfServe'),
    t('module.billing.entitlements.title'),
    t('module.billing.ledger.bucketDescription'),
    t('module.billing.ledger.bucketStatus.active'),
    t('module.billing.ledger.bucketStatus.canceled'),
    t('module.billing.ledger.bucketStatus.exhausted'),
    t('module.billing.ledger.bucketStatus.expired'),
    t('module.billing.ledger.category.free'),
    t('module.billing.ledger.category.subscription'),
    t('module.billing.ledger.category.topup'),
    t('module.billing.ledger.detail.balanceAfter'),
    t('module.billing.ledger.detail.billingMetric'),
    t('module.billing.ledger.detail.consumedCredits'),
    t('module.billing.ledger.detail.creditsPerUnit'),
    t('module.billing.ledger.detail.emptyBreakdown'),
    t('module.billing.ledger.detail.rawAmount'),
    t('module.billing.ledger.detail.roundingMode'),
    t('module.billing.ledger.detail.scene'),
    t('module.billing.ledger.detail.sourceBid'),
    t('module.billing.ledger.detail.title'),
    t('module.billing.ledger.detail.unitSize'),
    t('module.billing.ledger.detail.usageBid'),
    t('module.billing.ledger.entryType.adjustment'),
    t('module.billing.ledger.entryType.consume'),
    t('module.billing.ledger.entryType.expire'),
    t('module.billing.ledger.entryType.grant'),
    t('module.billing.ledger.entryType.hold'),
    t('module.billing.ledger.entryType.refund'),
    t('module.billing.ledger.entryType.release'),
    t('module.billing.ledger.entriesDescription'),
    t('module.billing.ledger.entriesTitle'),
    t('module.billing.ledger.empty'),
    t('module.billing.ledger.loadError'),
    t('module.billing.ledger.neverExpires'),
    t('module.billing.ledger.pagination.page'),
    t('module.billing.ledger.source.gift'),
    t('module.billing.ledger.source.manual'),
    t('module.billing.ledger.source.refund'),
    t('module.billing.ledger.source.subscription'),
    t('module.billing.ledger.source.topup'),
    t('module.billing.ledger.source.usage'),
    t('module.billing.ledger.summary.activeBuckets'),
    t('module.billing.ledger.summary.nextExpiry'),
    t('module.billing.ledger.summary.totalAvailable'),
    t('module.billing.ledger.table.action'),
    t('module.billing.ledger.table.amount'),
    t('module.billing.ledger.table.balanceAfter'),
    t('module.billing.ledger.table.createdAt'),
    t('module.billing.ledger.table.detail'),
    t('module.billing.ledger.table.entryType'),
    t('module.billing.ledger.table.availableCredits'),
    t('module.billing.ledger.table.effectiveWindow'),
    t('module.billing.ledger.table.priority'),
    t('module.billing.ledger.table.source'),
    t('module.billing.ledger.table.status'),
    t('module.billing.ledger.usageScene.debug'),
    t('module.billing.ledger.usageScene.preview'),
    t('module.billing.ledger.usageScene.production'),
    t('module.billing.orders.actions.sync'),
    t('module.billing.orders.empty'),
    t('module.billing.orders.loadError'),
    t('module.billing.orders.pagination.page'),
    t('module.billing.orders.paymentMode.oneTime'),
    t('module.billing.orders.paymentMode.subscription'),
    t('module.billing.orders.syncSuccess'),
    t('module.billing.orders.table.amount'),
    t('module.billing.orders.table.createdAt'),
    t('module.billing.orders.table.failure'),
    t('module.billing.orders.table.order'),
    t('module.billing.orders.table.provider'),
    t('module.billing.orders.table.status'),
    t('module.billing.orders.table.sync'),
    t('module.billing.orders.detail.emptyMetadata'),
    t('module.billing.orders.detail.fields.createdAt'),
    t('module.billing.orders.detail.fields.failedAt'),
    t('module.billing.orders.detail.fields.failureCode'),
    t('module.billing.orders.detail.fields.failureMessage'),
    t('module.billing.orders.detail.fields.orderBid'),
    t('module.billing.orders.detail.fields.orderType'),
    t('module.billing.orders.detail.fields.paidAmount'),
    t('module.billing.orders.detail.fields.paidAt'),
    t('module.billing.orders.detail.fields.payableAmount'),
    t('module.billing.orders.detail.fields.paymentMode'),
    t('module.billing.orders.detail.fields.productBid'),
    t('module.billing.orders.detail.fields.provider'),
    t('module.billing.orders.detail.fields.providerReferenceId'),
    t('module.billing.orders.detail.fields.refundedAt'),
    t('module.billing.orders.detail.fields.status'),
    t('module.billing.orders.detail.fields.subscriptionBid'),
    t('module.billing.orders.detail.loadError'),
    t('module.billing.orders.detail.sections.amounts'),
    t('module.billing.orders.detail.sections.metadata'),
    t('module.billing.orders.detail.sections.references'),
    t('module.billing.orders.detail.sections.summary'),
    t('module.billing.orders.detail.title'),
    t('module.billing.orders.type.manual'),
    t('module.billing.orders.type.refund'),
    t('module.billing.orders.type.subscriptionRenewal'),
    t('module.billing.orders.type.subscriptionStart'),
    t('module.billing.orders.type.subscriptionUpgrade'),
    t('module.billing.orders.type.topup'),
    t('module.billing.orders.status.canceled'),
    t('module.billing.orders.status.failed'),
    t('module.billing.orders.status.init'),
    t('module.billing.orders.status.paid'),
    t('module.billing.orders.status.pending'),
    t('module.billing.orders.status.refunded'),
    t('module.billing.orders.status.timeout'),
    t('module.billing.common.empty'),
    t('module.billing.page.adminLink'),
    t('module.billing.reports.description'),
    t('module.billing.reports.empty'),
    t('module.billing.reports.loadError'),
    t('module.billing.reports.metric.llmCacheTokens'),
    t('module.billing.reports.metric.llmInputTokens'),
    t('module.billing.reports.metric.llmOutputTokens'),
    t('module.billing.reports.metric.ttsInputChars'),
    t('module.billing.reports.metric.ttsOutputChars'),
    t('module.billing.reports.metric.ttsRequestCount'),
    t('module.billing.reports.pagination.page'),
    t('module.billing.reports.sections.ledger.description'),
    t('module.billing.reports.sections.ledger.title'),
    t('module.billing.reports.sections.usage.description'),
    t('module.billing.reports.sections.usage.title'),
    t('module.billing.reports.table.count'),
    t('module.billing.reports.table.credits'),
    t('module.billing.reports.table.date'),
    t('module.billing.reports.table.entryType'),
    t('module.billing.reports.table.metric'),
    t('module.billing.reports.table.provider'),
    t('module.billing.reports.table.rawAmount'),
    t('module.billing.reports.table.scene'),
    t('module.billing.reports.table.shifu'),
    t('module.billing.reports.table.source'),
    t('module.billing.reports.table.usageType'),
    t('module.billing.reports.table.window'),
    t('module.billing.reports.title'),
    t('module.billing.reports.usageType.llm'),
    t('module.billing.reports.usageType.tts'),
    t('module.billing.admin.attention'),
    t('module.billing.admin.domains.description'),
    t('module.billing.admin.domains.empty'),
    t('module.billing.admin.domains.loadError'),
    t('module.billing.admin.domains.table.creator'),
    t('module.billing.admin.domains.table.effective'),
    t('module.billing.admin.domains.table.entitlement'),
    t('module.billing.admin.domains.table.host'),
    t('module.billing.admin.domains.table.lastVerified'),
    t('module.billing.admin.domains.table.ssl'),
    t('module.billing.admin.domains.table.status'),
    t('module.billing.admin.domains.title'),
    t('module.billing.admin.domains.values.effective'),
    t('module.billing.admin.domains.values.inactive'),
    t('module.billing.admin.adjust.cancel'),
    t('module.billing.admin.adjust.description'),
    t('module.billing.admin.adjust.errors.amountInvalid'),
    t('module.billing.admin.adjust.errors.creatorBidRequired'),
    t('module.billing.admin.adjust.fields.amount'),
    t('module.billing.admin.adjust.fields.creatorBid'),
    t('module.billing.admin.adjust.fields.note'),
    t('module.billing.admin.adjust.help.amount'),
    t('module.billing.admin.adjust.open'),
    t('module.billing.admin.adjust.placeholders.amount'),
    t('module.billing.admin.adjust.placeholders.creatorBid'),
    t('module.billing.admin.adjust.placeholders.note'),
    t('module.billing.admin.adjust.quickAction'),
    t('module.billing.admin.adjust.submit'),
    t('module.billing.admin.adjust.submitting'),
    t('module.billing.admin.adjust.success'),
    t('module.billing.admin.backToCreatorBilling'),
    t('module.billing.admin.entitlements.description'),
    t('module.billing.admin.entitlements.empty'),
    t('module.billing.admin.entitlements.loadError'),
    t('module.billing.admin.entitlements.source.default'),
    t('module.billing.admin.entitlements.source.productPayload'),
    t('module.billing.admin.entitlements.source.snapshot'),
    t('module.billing.admin.entitlements.table.analytics'),
    t('module.billing.admin.entitlements.table.concurrency'),
    t('module.billing.admin.entitlements.table.creator'),
    t('module.billing.admin.entitlements.table.features'),
    t('module.billing.admin.entitlements.table.priority'),
    t('module.billing.admin.entitlements.table.source'),
    t('module.billing.admin.entitlements.table.support'),
    t('module.billing.admin.entitlements.table.window'),
    t('module.billing.admin.entitlements.title'),
    t('module.billing.admin.subtitle'),
    t('module.billing.admin.tabs.exceptions'),
    t('module.billing.admin.tabs.domains'),
    t('module.billing.admin.tabs.entitlements'),
    t('module.billing.admin.tabs.orders'),
    t('module.billing.admin.tabs.reports'),
    t('module.billing.admin.tabs.subscriptions'),
    t('module.billing.admin.title'),
    t('module.billing.admin.pagination.page'),
    t('module.billing.admin.subscriptions.description'),
    t('module.billing.admin.subscriptions.empty'),
    t('module.billing.admin.subscriptions.loadError'),
    t('module.billing.admin.subscriptions.table.availableCredits'),
    t('module.billing.admin.subscriptions.table.creator'),
    t('module.billing.admin.subscriptions.table.currentPeriodEnd'),
    t('module.billing.admin.subscriptions.table.product'),
    t('module.billing.admin.subscriptions.table.provider'),
    t('module.billing.admin.subscriptions.table.renewal'),
    t('module.billing.admin.subscriptions.table.scheduled'),
    t('module.billing.admin.subscriptions.table.renewalStatus'),
    t('module.billing.admin.subscriptions.table.status'),
    t('module.billing.admin.subscriptions.title'),
    t('module.billing.admin.orders.description'),
    t('module.billing.admin.orders.empty'),
    t('module.billing.admin.orders.loadError'),
    t('module.billing.admin.orders.table.amount'),
    t('module.billing.admin.orders.table.createdAt'),
    t('module.billing.admin.orders.table.creator'),
    t('module.billing.admin.orders.table.failure'),
    t('module.billing.admin.orders.table.order'),
    t('module.billing.admin.orders.table.provider'),
    t('module.billing.admin.orders.table.status'),
    t('module.billing.admin.orders.title'),
    t('module.billing.admin.reports.description'),
    t('module.billing.admin.reports.sections.ledger.description'),
    t('module.billing.admin.reports.sections.ledger.title'),
    t('module.billing.admin.reports.sections.usage.description'),
    t('module.billing.admin.reports.sections.usage.title'),
    t('module.billing.admin.reports.table.creator'),
    t('module.billing.admin.reports.title'),
    t('module.billing.admin.exceptions.description'),
    t('module.billing.admin.exceptions.empty'),
    t('module.billing.admin.exceptions.fields.amount'),
    t('module.billing.admin.exceptions.fields.createdAt'),
    t('module.billing.admin.exceptions.fields.detail'),
    t('module.billing.admin.exceptions.fields.periodEnd'),
    t('module.billing.admin.exceptions.fields.renewalEvent'),
    t('module.billing.admin.exceptions.loadError'),
    t('module.billing.admin.exceptions.sections.orders'),
    t('module.billing.admin.exceptions.sections.subscriptions'),
    t('module.billing.admin.exceptions.title'),
    t('module.billing.renewal.eventType.cancelEffective'),
    t('module.billing.renewal.eventType.downgradeEffective'),
    t('module.billing.renewal.eventType.expire'),
    t('module.billing.renewal.eventType.reconcile'),
    t('module.billing.renewal.eventType.renewal'),
    t('module.billing.renewal.eventType.retry'),
    t('module.billing.renewal.status.canceled'),
    t('module.billing.renewal.status.failed'),
    t('module.billing.renewal.status.pending'),
    t('module.billing.renewal.status.processing'),
    t('module.billing.renewal.status.succeeded'),
    t('module.billing.overview.actions.cancelSubscription'),
    t('module.billing.status.active'),
    t('module.billing.status.cancelScheduled'),
    t('module.billing.status.canceled'),
    t('module.billing.status.draft'),
    t('module.billing.status.expired'),
    t('module.billing.status.none'),
    t('module.billing.status.pastDue'),
    t('module.billing.status.paused'),
    t('module.billing.overview.actions.resumeSubscription'),
    t('module.billing.overview.feedback.cancelSuccess'),
    t('module.billing.overview.feedback.resumeSuccess'),
  ];
}
