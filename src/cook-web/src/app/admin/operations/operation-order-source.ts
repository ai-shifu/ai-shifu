import type {
  AdminOperationOrderItem,
  AdminOperationOrderSource,
} from './operation-order-types';

type OperationOrderSourceLike = Pick<
  AdminOperationOrderItem,
  | 'order_source'
  | 'order_source_key'
  | 'payment_channel'
  | 'coupon_codes'
  | 'paid_price'
>;

type TranslateOrderSource = (key: string) => string;

const ORDER_SOURCE_TRANSLATION_KEY_MAP: Record<string, string> = {
  user_purchase: 'source.userPurchase',
  coupon_redeem: 'source.couponRedeem',
  import_activation: 'source.importActivation',
  open_api: 'source.openApi',
};

export const normalizeOperationOrderSource = (
  order: OperationOrderSourceLike,
): AdminOperationOrderSource => {
  const normalizedSource = String(order.order_source || '').trim();
  if (normalizedSource) {
    return normalizedSource as AdminOperationOrderSource;
  }

  if (order.payment_channel === 'manual') {
    return 'import_activation';
  }

  if (order.payment_channel === 'open_api') {
    return 'open_api';
  }

  if (order.coupon_codes.length > 0 && Number(order.paid_price || 0) === 0) {
    return 'coupon_redeem';
  }

  return 'user_purchase';
};

export const getOperationOrderSourceLabel = (
  order: OperationOrderSourceLike,
  translate: TranslateOrderSource,
  fallbackLabel: string,
): string => {
  const normalizedSource = normalizeOperationOrderSource(order);
  const translationKey = ORDER_SOURCE_TRANSLATION_KEY_MAP[normalizedSource];

  if (translationKey) {
    return translate(translationKey);
  }

  return fallbackLabel;
};
