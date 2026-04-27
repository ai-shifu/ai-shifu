import type {
  BillingCapability,
  BillingCapabilityStatus,
  BillingBucketCategory,
  BillingBucketSourceType,
  BillingCheckoutResult,
  BillingLedgerEntryType,
  BillingLedgerItem,
  BillingMetricName,
  BillingOrderStatus,
  BillingOrderType,
  BillingPingxxChannel,
  BillingPlan,
  BillingPlanInterval,
  BillingProvider,
  BillingRenewalEventStatus,
  BillingRenewalEventSummary,
  BillingRenewalEventType,
  BillingSubscriptionStatus,
  BillingTrialOffer,
  BillingTopupProduct,
  BillingUsageScene,
  BillingUsageType,
} from '@/types/billing';

type BillingTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

const BILLING_PLAN_INTERVAL_LABEL_KEYS: Record<BillingPlanInterval, string> = {
  day: 'module.billing.catalog.labels.perDay',
  month: 'module.billing.catalog.labels.perMonth',
  year: 'module.billing.catalog.labels.perYear',
};

const BILLING_PLAN_INTERVAL_COUNT_LABEL_KEYS: Record<
  BillingPlanInterval,
  string
> = {
  day: 'module.billing.catalog.labels.everyDays',
  month: 'module.billing.catalog.labels.everyMonths',
  year: 'module.billing.catalog.labels.everyYears',
};

const BILLING_PLAN_CREDIT_SUMMARY_KEYS: Record<BillingPlanInterval, string> = {
  day: 'module.billing.package.creditSummary.daily',
  month: 'module.billing.package.creditSummary.monthly',
  year: 'module.billing.package.creditSummary.yearly',
};

const BILLING_PLAN_CREDIT_SUMMARY_COUNT_KEYS: Record<
  BillingPlanInterval,
  string
> = {
  day: 'module.billing.package.creditSummary.days',
  month: 'module.billing.package.creditSummary.months',
  year: 'module.billing.package.creditSummary.years',
};

const BILLING_PLAN_VALIDITY_KEYS: Record<BillingPlanInterval, string> = {
  day: 'module.billing.package.validity.daily',
  month: 'module.billing.package.validity.monthly',
  year: 'module.billing.package.validity.yearly',
};

const BILLING_PLAN_VALIDITY_COUNT_KEYS: Record<BillingPlanInterval, string> = {
  day: 'module.billing.package.validity.days',
  month: 'module.billing.package.validity.months',
  year: 'module.billing.package.validity.years',
};

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

const BILLING_CAPABILITY_STATUS_KEYS: Record<BillingCapabilityStatus, string> =
  {
    active: 'module.billing.capabilities.status.active',
    default_disabled: 'module.billing.capabilities.status.defaultDisabled',
    internal_only: 'module.billing.capabilities.status.internalOnly',
  };

const BILLING_CAPABILITY_TITLE_KEYS: Record<string, string> = {
  creator_catalog: 'module.billing.capabilities.items.creatorCatalog.title',
  creator_subscription_checkout:
    'module.billing.capabilities.items.creatorSubscriptionCheckout.title',
  creator_wallet_ledger:
    'module.billing.capabilities.items.creatorWalletLedger.title',
  creator_orders: 'module.billing.capabilities.items.creatorOrders.title',
  admin_subscriptions:
    'module.billing.capabilities.items.adminSubscriptions.title',
  admin_orders: 'module.billing.capabilities.items.adminOrders.title',
  admin_ledger_adjust:
    'module.billing.capabilities.items.adminLedgerAdjust.title',
  admin_entitlements:
    'module.billing.capabilities.items.adminEntitlements.title',
  admin_domains: 'module.billing.capabilities.items.adminDomains.title',
  admin_reports: 'module.billing.capabilities.items.adminReports.title',
  runtime_billing_extensions:
    'module.billing.capabilities.items.runtimeBillingExtensions.title',
  billing_feature_flag:
    'module.billing.capabilities.items.billingFeatureFlag.title',
  renewal_task_queue:
    'module.billing.capabilities.items.renewalTaskQueue.title',
  usage_settlement: 'module.billing.capabilities.items.usageSettlement.title',
  renewal_compensation:
    'module.billing.capabilities.items.renewalCompensation.title',
  provider_reconcile:
    'module.billing.capabilities.items.providerReconcile.title',
  wallet_bucket_expiration:
    'module.billing.capabilities.items.walletBucketExpiration.title',
  low_balance_alerts:
    'module.billing.capabilities.items.lowBalanceAlerts.title',
  daily_aggregate_rebuild:
    'module.billing.capabilities.items.dailyAggregateRebuild.title',
  domain_verify_refresh:
    'module.billing.capabilities.items.domainVerifyRefresh.title',
};

const BILLING_CAPABILITY_DESCRIPTION_KEYS: Record<string, string> = {
  creator_catalog:
    'module.billing.capabilities.items.creatorCatalog.description',
  creator_subscription_checkout:
    'module.billing.capabilities.items.creatorSubscriptionCheckout.description',
  creator_wallet_ledger:
    'module.billing.capabilities.items.creatorWalletLedger.description',
  creator_orders: 'module.billing.capabilities.items.creatorOrders.description',
  admin_subscriptions:
    'module.billing.capabilities.items.adminSubscriptions.description',
  admin_orders: 'module.billing.capabilities.items.adminOrders.description',
  admin_ledger_adjust:
    'module.billing.capabilities.items.adminLedgerAdjust.description',
  admin_entitlements:
    'module.billing.capabilities.items.adminEntitlements.description',
  admin_domains: 'module.billing.capabilities.items.adminDomains.description',
  admin_reports: 'module.billing.capabilities.items.adminReports.description',
  runtime_billing_extensions:
    'module.billing.capabilities.items.runtimeBillingExtensions.description',
  billing_feature_flag:
    'module.billing.capabilities.items.billingFeatureFlag.description',
  renewal_task_queue:
    'module.billing.capabilities.items.renewalTaskQueue.description',
  usage_settlement:
    'module.billing.capabilities.items.usageSettlement.description',
  renewal_compensation:
    'module.billing.capabilities.items.renewalCompensation.description',
  provider_reconcile:
    'module.billing.capabilities.items.providerReconcile.description',
  wallet_bucket_expiration:
    'module.billing.capabilities.items.walletBucketExpiration.description',
  low_balance_alerts:
    'module.billing.capabilities.items.lowBalanceAlerts.description',
  daily_aggregate_rebuild:
    'module.billing.capabilities.items.dailyAggregateRebuild.description',
  domain_verify_refresh:
    'module.billing.capabilities.items.domainVerifyRefresh.description',
};

const BILLING_BUCKET_CATEGORY_KEYS: Record<BillingBucketCategory, string> = {
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

const BILLING_USAGE_TYPE_CODE_MAP: Record<number, BillingUsageType> = {
  1101: 'llm',
  1102: 'tts',
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
  manual: 'module.billing.catalog.labels.providerManual',
  stripe: 'module.billing.catalog.labels.providerStripe',
  pingxx: 'module.billing.catalog.labels.providerPingxx',
  alipay: 'module.billing.catalog.labels.providerAlipay',
  wechatpay: 'module.billing.catalog.labels.providerWechatpay',
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

const BILLING_OFFSETLESS_DATETIME_RE =
  /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2}(?:\.\d+)?)$/;
const BILLING_LEGACY_SOURCE_OFFSET = '+08:00';
const DEFAULT_BILL_CREDIT_PRECISION = 2;
const MAX_BILL_CREDIT_PRECISION = 10;

let billingCreditPrecision = DEFAULT_BILL_CREDIT_PRECISION;

function normalizeBillingCreditPrecision(value?: number | null): number {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return DEFAULT_BILL_CREDIT_PRECISION;
  }
  return Math.min(
    MAX_BILL_CREDIT_PRECISION,
    Math.max(0, Math.trunc(numericValue)),
  );
}

export function setBillingCreditPrecision(value?: number | null): void {
  billingCreditPrecision = normalizeBillingCreditPrecision(value);
}

export function formatBillingCredits(
  value: number,
  locale: string,
  precision: number = billingCreditPrecision,
): string {
  const normalizedPrecision = normalizeBillingCreditPrecision(precision);
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: normalizedPrecision,
    maximumFractionDigits: normalizedPrecision,
  }).format(Number(value || 0));
}

export function formatBillingCreditBalance(value: number): string {
  return String(Math.trunc(Number(value || 0)));
}

export function formatBillingCreditAmount(value: number): string {
  return String(Math.trunc(Number(value || 0)));
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

export function resolveBillingCapabilityStatusLabel(
  t: BillingTranslator,
  status: BillingCapabilityStatus,
): string {
  return t(BILLING_CAPABILITY_STATUS_KEYS[status]);
}

export function resolveBillingCapabilityTitle(
  t: BillingTranslator,
  capability: BillingCapability,
): string {
  return t(
    BILLING_CAPABILITY_TITLE_KEYS[capability.key] ||
      'module.billing.capabilities.fallbackTitle',
  );
}

export function resolveBillingCapabilityDescription(
  t: BillingTranslator,
  capability: BillingCapability,
): string {
  return t(
    BILLING_CAPABILITY_DESCRIPTION_KEYS[capability.key] ||
      'module.billing.capabilities.fallbackDescription',
  );
}

export function resolveBillingProductTitle(
  t: BillingTranslator,
  product?: BillingPlan | BillingTopupProduct | BillingTrialOffer | null,
  fallback = '',
): string {
  if (!product?.display_name) {
    return fallback;
  }
  return t(product.display_name);
}

export function resolveBillingProductDescription(
  t: BillingTranslator,
  product?: BillingPlan | BillingTopupProduct | BillingTrialOffer | null,
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

export function buildBillingSwrKey(
  baseKey: string,
  timezone: string,
  ...parts: unknown[]
) {
  return [baseKey, ...parts, timezone || ''] as const;
}

export function withBillingTimezone<T extends Record<string, unknown>>(
  params: T,
  timezone: string,
): T & { timezone?: string } {
  if (!timezone) {
    return params;
  }

  return {
    ...params,
    timezone,
  };
}

export function parseBillingDateValue(
  value: string | null | undefined,
): Date | null {
  if (!value) {
    return null;
  }

  const normalizedValue = String(value).trim();
  if (!normalizedValue) {
    return null;
  }

  const legacyOffsetlessMatch = normalizedValue.match(
    BILLING_OFFSETLESS_DATETIME_RE,
  );
  const candidateValue = legacyOffsetlessMatch
    ? `${legacyOffsetlessMatch[1]}T${legacyOffsetlessMatch[2]}${BILLING_LEGACY_SOURCE_OFFSET}`
    : normalizedValue;

  const date = new Date(candidateValue);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date;
}

export function formatBillingExpiryCountdown(
  t: BillingTranslator,
  value: string | null | undefined,
): string {
  const date = parseBillingDateValue(value);
  if (!date) return '';

  const now = new Date();
  const msPerDay = 1000 * 60 * 60 * 24;
  const daysLeft = Math.ceil((date.getTime() - now.getTime()) / msPerDay);

  if (daysLeft <= 0) return t('module.billing.sidebar.expired');
  return t('module.billing.sidebar.expiresInDays', { days: daysLeft });
}

export function formatBillingDate(
  value: string | null | undefined,
  locale: string,
): string {
  const date = parseBillingDateValue(value);
  if (!date) {
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
  const date = parseBillingDateValue(value);
  if (!date) {
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

export function formatBillingCompactDateTime(
  value: string | null | undefined,
  locale: string,
): string {
  const date = parseBillingDateValue(value);
  if (!date) {
    return '';
  }

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');

  if (locale.toLowerCase().startsWith('zh')) {
    return `${year}年${month}月${day}日 ${hour}:${minute}`;
  }

  return `${year}-${month}-${day} ${hour}:${minute}`;
}

export function formatBillingPlanInterval(
  t: BillingTranslator,
  product: BillingPlan,
): string {
  const intervalCount = Math.max(product.billing_interval_count || 0, 1);
  if (intervalCount > 1) {
    return t(BILLING_PLAN_INTERVAL_COUNT_LABEL_KEYS[product.billing_interval], {
      count: intervalCount,
    });
  }
  return t(BILLING_PLAN_INTERVAL_LABEL_KEYS[product.billing_interval]);
}

export function resolveBillingPlanCreditsLabel(
  t: BillingTranslator,
  product: BillingPlan,
): string {
  const intervalCount = Math.max(product.billing_interval_count || 0, 1);
  return t(
    intervalCount > 1
      ? BILLING_PLAN_CREDIT_SUMMARY_COUNT_KEYS[product.billing_interval]
      : BILLING_PLAN_CREDIT_SUMMARY_KEYS[product.billing_interval],
    {
      count: intervalCount,
      credits: formatBillingCreditAmount(product.credit_amount),
    },
  );
}

export function resolveBillingPlanValidityLabel(
  t: BillingTranslator,
  product: BillingPlan,
): string {
  const intervalCount = Math.max(product.billing_interval_count || 0, 1);
  return t(
    intervalCount > 1
      ? BILLING_PLAN_VALIDITY_COUNT_KEYS[product.billing_interval]
      : BILLING_PLAN_VALIDITY_KEYS[product.billing_interval],
    {
      count: intervalCount,
    },
  );
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

export function resolveBillingLedgerEntryLabel(
  t: BillingTranslator,
  entryType: BillingLedgerEntryType,
): string {
  return t(BILLING_LEDGER_ENTRY_KEYS[entryType]);
}

export function resolveBillingLedgerReasonLabel(
  t: BillingTranslator,
  item: Pick<BillingLedgerItem, 'entry_type' | 'source_type' | 'metadata'> &
    Partial<BillingLedgerItem>,
): string {
  if (item.entry_type === 'expire') {
    return resolveBillingLedgerEntryLabel(t, item.entry_type);
  }

  if (item.entry_type === 'hold' || item.entry_type === 'release') {
    return resolveBillingLedgerEntryLabel(t, item.entry_type);
  }

  if (item.source_type === 'usage') {
    const usageType = resolveBillingLedgerUsageType(item.metadata);
    const usageScene = item.metadata?.usage_scene;
    const usageSceneLabel = resolveBillingUsageSceneLabel(
      t,
      usageScene === 'preview' ? 'debug' : usageScene,
    );
    const courseName = String(item.metadata?.course_name || '').trim();
    const userIdentify = String(item.metadata?.user_identify || '').trim();
    const shouldShowUserIdentify = Boolean(
      userIdentify &&
      (usageScene === 'production' ||
        usageScene === 'debug' ||
        usageScene === 'preview'),
    );

    if (usageType === 'tts') {
      const reasonParts = [t('module.billing.ledger.usageScene.tts')];

      if (courseName) {
        reasonParts.push(courseName);
      }
      if (shouldShowUserIdentify) {
        reasonParts.push(userIdentify);
      }
      return reasonParts.join(' - ');
    }

    if (usageSceneLabel) {
      const reasonParts = [usageSceneLabel];

      if (courseName) {
        reasonParts.push(courseName);
      }
      if (shouldShowUserIdentify) {
        reasonParts.push(userIdentify);
      }
      return reasonParts.join(' - ');
    }
  }

  const sourceLabel = resolveBillingBucketSourceLabel(t, item.source_type);
  if (sourceLabel) {
    return sourceLabel;
  }

  return resolveBillingLedgerEntryLabel(t, item.entry_type);
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

export function resolveBillingLedgerUsageType(
  metadata?: BillingLedgerItem['metadata'] | null,
): BillingUsageType | null {
  const rawUsageType = metadata?.usage_type;
  if (rawUsageType === 'llm' || rawUsageType === 'tts') {
    return rawUsageType;
  }

  const numericUsageType = Number(rawUsageType);
  if (Number.isFinite(numericUsageType)) {
    return BILLING_USAGE_TYPE_CODE_MAP[numericUsageType] || null;
  }

  const metricBreakdown = metadata?.metric_breakdown || [];
  if (
    metricBreakdown.some(item =>
      String(item.billing_metric || '').startsWith('tts_'),
    )
  ) {
    return 'tts';
  }
  if (
    metricBreakdown.some(item =>
      String(item.billing_metric || '').startsWith('llm_'),
    )
  ) {
    return 'llm';
  }
  return null;
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

export function resolveBillingPingxxChannelLabel(
  t: BillingTranslator,
  channel: BillingPingxxChannel,
): string {
  return channel === 'wx_pub_qr'
    ? t('module.pay.wechatPay')
    : t('module.pay.alipay');
}

export function extractBillingPingxxQrCode(
  result: BillingCheckoutResult,
  preferredChannel: BillingPingxxChannel = 'wx_pub_qr',
): { channel: BillingPingxxChannel; url: string } | null {
  const credential =
    typeof result.payment_payload === 'object' && result.payment_payload
      ? (result.payment_payload as Record<string, unknown>).credential
      : null;
  if (!credential || typeof credential !== 'object') {
    return null;
  }

  const normalizedCredential = credential as Record<string, unknown>;
  const channels: BillingPingxxChannel[] =
    preferredChannel === 'wx_pub_qr'
      ? ['wx_pub_qr', 'alipay_qr']
      : ['alipay_qr', 'wx_pub_qr'];

  for (const channel of channels) {
    const qrUrl = normalizedCredential[channel];
    if (typeof qrUrl === 'string' && qrUrl) {
      return { channel, url: qrUrl };
    }
  }

  return null;
}

export function registerBillingTranslationUsage(t: BillingTranslator): void {
  void [
    t('module.billing.capabilities.fallbackDescription'),
    t('module.billing.capabilities.fallbackTitle'),
    t('module.billing.capabilities.items.adminDomains.description'),
    t('module.billing.capabilities.items.adminDomains.title'),
    t('module.billing.capabilities.items.adminEntitlements.description'),
    t('module.billing.capabilities.items.adminEntitlements.title'),
    t('module.billing.capabilities.items.adminLedgerAdjust.description'),
    t('module.billing.capabilities.items.adminLedgerAdjust.title'),
    t('module.billing.capabilities.items.adminOrders.description'),
    t('module.billing.capabilities.items.adminOrders.title'),
    t('module.billing.capabilities.items.adminReports.description'),
    t('module.billing.capabilities.items.adminReports.title'),
    t('module.billing.capabilities.items.adminSubscriptions.description'),
    t('module.billing.capabilities.items.adminSubscriptions.title'),
    t('module.billing.capabilities.items.billingFeatureFlag.description'),
    t('module.billing.capabilities.items.billingFeatureFlag.title'),
    t('module.billing.capabilities.items.creatorCatalog.description'),
    t('module.billing.capabilities.items.creatorCatalog.title'),
    t('module.billing.capabilities.items.creatorOrders.description'),
    t('module.billing.capabilities.items.creatorOrders.title'),
    t(
      'module.billing.capabilities.items.creatorSubscriptionCheckout.description',
    ),
    t('module.billing.capabilities.items.creatorSubscriptionCheckout.title'),
    t('module.billing.capabilities.items.creatorWalletLedger.description'),
    t('module.billing.capabilities.items.creatorWalletLedger.title'),
    t('module.billing.capabilities.items.dailyAggregateRebuild.description'),
    t('module.billing.capabilities.items.dailyAggregateRebuild.title'),
    t('module.billing.capabilities.items.domainVerifyRefresh.description'),
    t('module.billing.capabilities.items.domainVerifyRefresh.title'),
    t('module.billing.capabilities.items.lowBalanceAlerts.description'),
    t('module.billing.capabilities.items.lowBalanceAlerts.title'),
    t('module.billing.capabilities.items.providerReconcile.description'),
    t('module.billing.capabilities.items.providerReconcile.title'),
    t('module.billing.capabilities.items.renewalCompensation.description'),
    t('module.billing.capabilities.items.renewalCompensation.title'),
    t('module.billing.capabilities.items.renewalTaskQueue.description'),
    t('module.billing.capabilities.items.renewalTaskQueue.title'),
    t('module.billing.capabilities.items.runtimeBillingExtensions.description'),
    t('module.billing.capabilities.items.runtimeBillingExtensions.title'),
    t('module.billing.capabilities.items.usageSettlement.description'),
    t('module.billing.capabilities.items.usageSettlement.title'),
    t('module.billing.capabilities.items.walletBucketExpiration.description'),
    t('module.billing.capabilities.items.walletBucketExpiration.title'),
    t('module.billing.capabilities.status.active'),
    t('module.billing.capabilities.status.defaultDisabled'),
    t('module.billing.capabilities.status.internalOnly'),
    t('module.billing.catalog.badges.bestValue'),
    t('module.billing.catalog.badges.recommended'),
    t('module.billing.catalog.labels.everyDays', { count: 7 }),
    t('module.billing.catalog.labels.everyMonths', { count: 3 }),
    t('module.billing.catalog.labels.everyYears', { count: 2 }),
    t('module.billing.catalog.labels.perDay'),
    t('module.billing.catalog.labels.perMonth'),
    t('module.billing.catalog.labels.perYear'),
    t('module.billing.catalog.labels.providerManual'),
    t('module.billing.catalog.plans.creatorMonthly.description'),
    t('module.billing.catalog.plans.creatorMonthly.title'),
    t('module.billing.catalog.plans.creatorMonthlyPro.description'),
    t('module.billing.catalog.plans.creatorMonthlyPro.title'),
    t('module.billing.catalog.plans.creatorYearly.description'),
    t('module.billing.catalog.plans.creatorYearly.title'),
    t('module.billing.catalog.plans.creatorYearlyLite.description'),
    t('module.billing.catalog.plans.creatorYearlyLite.title'),
    t('module.billing.catalog.plans.creatorYearlyPremium.description'),
    t('module.billing.catalog.plans.creatorYearlyPremium.title'),
    t('module.billing.catalog.topups.creatorLarge.description'),
    t('module.billing.catalog.topups.creatorLarge.title'),
    t('module.billing.catalog.topups.creatorMedium.description'),
    t('module.billing.catalog.topups.creatorMedium.title'),
    t('module.billing.catalog.topups.creatorSmall.description'),
    t('module.billing.catalog.topups.creatorSmall.title'),
    t('module.billing.catalog.topups.creatorXLarge.description'),
    t('module.billing.catalog.topups.creatorXLarge.title'),
    t('module.billing.details.subtitle'),
    t('module.billing.overview.availableCreditsLabel'),
    t('module.billing.overview.walletTitle'),
    t('module.billing.package.actions.currentUsing'),
    t('module.billing.package.actions.freeTrial'),
    t('module.billing.package.creditSummary.daily'),
    t('module.billing.package.creditSummary.days', { count: 7, credits: '7' }),
    t('module.billing.package.creditSummary.monthly'),
    t('module.billing.package.creditSummary.months', {
      count: 3,
      credits: '9',
    }),
    t('module.billing.package.creditSummary.yearly'),
    t('module.billing.package.creditSummary.years', {
      count: 2,
      credits: '24',
    }),
    t('module.billing.package.free.creditSummary'),
    t('module.billing.package.free.description'),
    t('module.billing.package.free.priceNote'),
    t('module.billing.package.free.priceNoteGranted'),
    t('module.billing.package.free.priceValue'),
    t('module.billing.package.free.title'),
    t('module.billing.package.subtitle'),
    t('module.billing.package.topupComingSoon'),
    t('module.billing.package.topup.noteFrozen'),
    t('module.billing.package.topup.noteInstant'),
    t('module.billing.package.topup.noteTitle'),
    t('module.billing.package.scale.advanced.students'),
    t('module.billing.package.scale.basic.students'),
    t('module.billing.package.scale.free.students'),
    t('module.billing.package.scale.lite.students'),
    t('module.billing.package.scale.premium.students'),
    t('module.billing.package.scale.pro.students'),
    t('module.billing.package.scale.sectionTitle'),
    t('module.billing.package.features.advanced.includesLabel'),
    t('module.billing.package.features.advanced.parallelProcessing'),
    t('module.billing.package.features.advanced.taskPriority'),
    t('module.billing.package.features.advanced.techBasic'),
    t('module.billing.package.features.daily.preview'),
    t('module.billing.package.features.daily.publish'),
    t('module.billing.package.features.daily.support'),
    t('module.billing.package.features.free.preview'),
    t('module.billing.package.features.free.publish'),
    t('module.billing.package.intervalTabs.daily'),
    t('module.billing.package.validity.daily'),
    t('module.billing.package.validity.days', { count: 7 }),
    t('module.billing.package.validity.monthly'),
    t('module.billing.package.validity.months', { count: 3 }),
    t('module.billing.package.validity.yearly'),
    t('module.billing.package.validity.years', { count: 2 }),
    t('module.billing.package.features.monthly.preview'),
    t('module.billing.package.features.monthly.publish'),
    t('module.billing.package.features.yearly.lite.ops'),
    t('module.billing.package.features.yearly.lite.publish'),
    t('module.billing.package.features.yearly.pro.analytics'),
    t('module.billing.package.features.yearly.pro.branding'),
    t('module.billing.package.features.yearly.pro.domain'),
    t('module.billing.package.features.yearly.pro.priority'),
    t('module.billing.package.features.yearly.pro.support'),
    t('module.billing.package.features.yearly.premium.analytics'),
    t('module.billing.package.features.yearly.premium.branding'),
    t('module.billing.package.features.yearly.premium.domain'),
    t('module.billing.package.features.yearly.premium.priority'),
    t('module.billing.package.features.yearly.premium.support'),
    t('module.billing.package.features.premium.concurrencyQuota'),
    t('module.billing.package.features.premium.dedicatedSupport'),
    t('module.billing.package.features.premium.includesLabel'),
    t('module.billing.package.features.premium.onboarding'),
    t('module.billing.package.features.pro.branding'),
    t('module.billing.package.features.pro.customDomain'),
    t('module.billing.package.features.pro.includesLabel'),
    t('module.billing.package.features.pro.techPriority'),
    t('module.billing.alerts.actions.checkoutTopup'),
    t('module.billing.alerts.actions.openOrders'),
    t('module.billing.alerts.actions.resumeSubscription'),
    t('module.billing.alerts.cancelScheduled'),
    t('module.billing.alerts.lowBalance'),
    t('module.billing.alerts.subscriptionPastDue'),
    t('module.billing.checkout.planDescription'),
    t('module.billing.checkout.subject.plan.day'),
    t('module.billing.checkout.subject.plan.month'),
    t('module.billing.checkout.subject.plan.year'),
    t('module.billing.checkout.topupDescription'),
    t('module.billing.domains.records.neverVerified'),
    t('module.billing.domains.ssl.issued'),
    t('module.billing.domains.ssl.not_requested'),
    t('module.billing.domains.ssl.pending'),
    t('module.billing.domains.status.disabled'),
    t('module.billing.domains.status.failed'),
    t('module.billing.domains.status.pending'),
    t('module.billing.domains.status.verified'),
    t('module.billing.entitlements.analytics.advanced'),
    t('module.billing.entitlements.analytics.basic'),
    t('module.billing.entitlements.analytics.enterprise'),
    t('module.billing.entitlements.flags.branding'),
    t('module.billing.entitlements.flags.customDomain'),
    t('module.billing.entitlements.flags.disabled'),
    t('module.billing.entitlements.flags.enabled'),
    t('module.billing.entitlements.metrics.analyticsTier'),
    t('module.billing.entitlements.metrics.maxConcurrency'),
    t('module.billing.entitlements.metrics.priorityClass'),
    t('module.billing.entitlements.metrics.supportTier'),
    t('module.billing.entitlements.priority.priority'),
    t('module.billing.entitlements.priority.standard'),
    t('module.billing.entitlements.priority.vip'),
    t('module.billing.entitlements.support.businessHours'),
    t('module.billing.entitlements.support.priority'),
    t('module.billing.entitlements.support.selfServe'),
    t('module.billing.ledger.bucketDescription'),
    t('module.billing.ledger.category.subscription'),
    t('module.billing.ledger.category.topup'),
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
    t('module.billing.ledger.usageScene.tts'),
    t('module.billing.page.tabs.plans'),
    t('module.billing.sidebar.cta'),
    t('module.billing.sidebar.creditsLabel'),
    t('module.billing.sidebar.dailyBalanceTitle'),
    t('module.billing.sidebar.dailyTitle'),
    t('module.billing.sidebar.description'),
    t('module.billing.sidebar.monthlyTitle'),
    t('module.billing.sidebar.monthlyBalanceTitle'),
    t('module.billing.sidebar.nonMemberBalanceTitle'),
    t('module.billing.sidebar.nonMemberTitle'),
    t('module.billing.sidebar.subscriptionPending'),
    t('module.billing.sidebar.subscriptionStatusLabel'),
    t('module.billing.sidebar.yearlyBalanceTitle'),
    t('module.billing.sidebar.yearlyTitle'),
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
    t('module.billing.reports.empty'),
    t('module.billing.reports.loadError'),
    t('module.billing.reports.metric.llmCacheTokens'),
    t('module.billing.reports.metric.llmInputTokens'),
    t('module.billing.reports.metric.llmOutputTokens'),
    t('module.billing.reports.metric.ttsInputChars'),
    t('module.billing.reports.metric.ttsOutputChars'),
    t('module.billing.reports.metric.ttsRequestCount'),
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
    t('module.billing.status.active'),
    t('module.billing.status.cancelScheduled'),
    t('module.billing.status.canceled'),
    t('module.billing.status.draft'),
    t('module.billing.status.expired'),
    t('module.billing.status.none'),
    t('module.billing.status.pastDue'),
    t('module.billing.status.paused'),
    t('module.billing.overview.feedback.cancelSuccess'),
    t('module.billing.overview.feedback.resumeSuccess'),
  ];
}
