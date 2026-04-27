import {
  formatBillingDateTime,
  resolveBillingPingxxChannelLabel,
  resolveBillingProviderLabel,
} from '@/lib/billing';
import type { BillingPingxxChannel, BillingProvider } from '@/types/billing';
import type {
  AdminOperationCreditOrderItem,
  OperationCreditOrderKind,
} from './operation-credit-order-types';

type Translator = (key: string, options?: Record<string, unknown>) => string;
type CreditOrderPlanInterval = 'day' | 'month' | 'year';

const BILLING_PROVIDERS = [
  'manual',
  'pingxx',
  'stripe',
] as const satisfies readonly BillingProvider[];
const PINGXX_CHANNELS = [
  'wx_pub_qr',
  'alipay_qr',
] as const satisfies readonly BillingPingxxChannel[];

/**
 * t('module.operationsOrder.creditOrders.productIntervals.day')
 * t('module.operationsOrder.creditOrders.productIntervals.month')
 * t('module.operationsOrder.creditOrders.productIntervals.year')
 * t('module.operationsOrder.creditOrders.productNameFormat')
 */

function isBillingProvider(value: string): value is BillingProvider {
  return (BILLING_PROVIDERS as readonly string[]).includes(value);
}

function isPingxxChannel(value: string): value is BillingPingxxChannel {
  return (PINGXX_CHANNELS as readonly string[]).includes(value);
}

function translateIfResolved(
  t: Translator,
  key: string,
  options?: Record<string, unknown>,
): string {
  if (!key) {
    return '';
  }

  const translated = t(key, options);
  if (!translated || translated === key) {
    return '';
  }
  return translated;
}

function resolvePlanIntervalFromProduct(
  order: Pick<AdminOperationCreditOrderItem, 'product_name_key' | 'product_code'>,
): CreditOrderPlanInterval | '' {
  const compositeKey = `${String(order.product_name_key || '')} ${String(order.product_code || '')}`.toLowerCase();

  if (compositeKey.includes('daily')) {
    return 'day';
  }
  if (compositeKey.includes('monthly')) {
    return 'month';
  }
  if (compositeKey.includes('yearly')) {
    return 'year';
  }
  return '';
}

export function resolveOperationCreditOrderKindLabel(
  t: Translator,
  kind: OperationCreditOrderKind,
): string {
  const normalizedKind = kind === 'plan' || kind === 'topup' ? kind : 'other';
  return t(`module.operationsOrder.creditOrders.kind.${normalizedKind}`);
}

export function resolveOperationCreditOrderProviderLabel(
  t: Translator,
  provider: string,
): string {
  if (isBillingProvider(provider)) {
    return resolveBillingProviderLabel(t, provider);
  }
  return provider || t('module.order.paymentChannel.unknown');
}

export function resolveOperationCreditOrderPaymentChannelLabel(
  t: Translator,
  order: Pick<
    AdminOperationCreditOrderItem,
    'payment_provider' | 'payment_channel'
  >,
): string {
  const providerLabel = resolveOperationCreditOrderProviderLabel(
    t,
    String(order.payment_provider || ''),
  );
  const channel = String(order.payment_channel || '').trim();

  if (!channel || channel === order.payment_provider) {
    return providerLabel;
  }

  if (isPingxxChannel(channel)) {
    return `${providerLabel} / ${resolveBillingPingxxChannelLabel(t, channel)}`;
  }

  if (channel === 'checkout_session') {
    return `${providerLabel} / ${t('module.operationsOrder.creditOrders.paymentChannel.checkoutSession')}`;
  }

  return `${providerLabel} / ${channel}`;
}

export function resolveOperationCreditOrderProductName(
  t: Translator,
  order: Pick<
    AdminOperationCreditOrderItem,
    'credit_order_kind' | 'product_name_key' | 'product_code'
  >,
  fallback: string,
): string {
  const translatedName = translateIfResolved(t, String(order.product_name_key || ''));

  if (order.credit_order_kind === 'plan') {
    const interval = resolvePlanIntervalFromProduct(order);
    const intervalLabel = interval
      ? translateIfResolved(
          t,
          `module.operationsOrder.creditOrders.productIntervals.${interval}`,
        )
      : '';

    if (intervalLabel && translatedName) {
      return (
        translateIfResolved(
          t,
          'module.operationsOrder.creditOrders.productNameFormat',
          {
            interval: intervalLabel,
            name: translatedName,
          },
        ) || `${intervalLabel}-${translatedName}`
      );
    }
  }

  if (translatedName) {
    return translatedName;
  }

  return order.product_code || fallback;
}

export function resolveOperationCreditOrderValidityLabel(
  t: Translator,
  locale: string,
  validFrom: string | null | undefined,
  validTo: string | null | undefined,
  fallback: string,
): string {
  if (validTo) {
    return formatBillingDateTime(validTo, locale) || fallback;
  }
  if (validFrom) {
    return t('module.operationsOrder.creditOrders.longTerm');
  }
  return fallback;
}
