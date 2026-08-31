import {
  getOperationOrderSourceLabel,
  normalizeOperationOrderSource,
} from './operation-order-source';

const buildOrder = (
  overrides?: Partial<{
    order_source: string;
    order_source_key: string;
    payment_channel: string;
    coupon_codes: string[];
    paid_price: string;
  }>,
) => ({
  order_source: '',
  order_source_key: '',
  payment_channel: '',
  coupon_codes: [],
  paid_price: '1',
  ...overrides,
});

describe('normalizeOperationOrderSource', () => {
  test('prefers explicit backend source', () => {
    expect(
      normalizeOperationOrderSource(
        buildOrder({
          order_source: 'coupon_redeem',
          payment_channel: 'stripe',
        }),
      ),
    ).toBe('coupon_redeem');
  });

  test('falls back to manual and open api payment channels', () => {
    expect(
      normalizeOperationOrderSource(buildOrder({ payment_channel: 'manual' })),
    ).toBe('import_activation');
    expect(
      normalizeOperationOrderSource(
        buildOrder({ payment_channel: 'open_api' }),
      ),
    ).toBe('open_api');
  });

  test('falls back to coupon redeem when zero paid order has coupon codes', () => {
    expect(
      normalizeOperationOrderSource(
        buildOrder({ coupon_codes: ['FREE100'], paid_price: '0' }),
      ),
    ).toBe('coupon_redeem');
  });

  test('defaults to user purchase', () => {
    expect(normalizeOperationOrderSource(buildOrder())).toBe('user_purchase');
  });
});

describe('getOperationOrderSourceLabel', () => {
  test('prefers backend translation key when provided', () => {
    const translate = (key: string) => `translated:${key}`;

    expect(
      getOperationOrderSourceLabel(
        buildOrder({
          order_source: 'user_purchase',
          order_source_key: 'module.operationsOrder.source.couponRedeem',
        }),
        translate,
        '--',
      ),
    ).toBe('translated:source.couponRedeem');
  });

  test('maps normalized source with translation function', () => {
    const translate = (key: string) => `translated:${key}`;

    expect(
      getOperationOrderSourceLabel(
        buildOrder({ order_source: 'user_purchase' }),
        translate,
        '--',
      ),
    ).toBe('translated:source.userPurchase');
  });

  test('falls back to empty label for unknown sources', () => {
    expect(
      getOperationOrderSourceLabel(
        buildOrder({
          order_source: 'unexpected_source',
          order_source_key: 'module.operationsOrder.source.unknown',
        }),
        key => key,
        '--',
      ),
    ).toBe('--');
  });
});
