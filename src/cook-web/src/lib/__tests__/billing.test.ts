import {
  formatBillingCreditAmount,
  formatBillingCreditBalance,
  formatBillingCreditDetail,
  formatBillingCredits,
  formatBillingNumber,
  formatBillingPlanInterval,
  formatBillingPrice,
  extractBillingPingxxQrCode,
  parseBillingDateValue,
  resolveBillingLedgerUsageType,
  resolveBillingLedgerReasonLabel,
  resolveBillingPlanCreditsLabel,
  resolveBillingPlanValidityLabel,
} from '@/lib/billing';
import type { BillingLedgerItem, BillingPlan } from '@/types/billing';
import type { BillingCheckoutResult } from '@/types/billing';

const monthlyPlan: BillingPlan = {
  product_bid: 'bill-product-plan-monthly',
  product_code: 'creator-plan-monthly',
  product_type: 'plan',
  display_name: 'module.billing.catalog.plans.creatorMonthly.title',
  description: 'module.billing.catalog.plans.creatorMonthly.description',
  billing_interval: 'month',
  billing_interval_count: 1,
  currency: 'CNY',
  price_amount: 990,
  credit_amount: 5,
  auto_renew_enabled: true,
};

const yearlyPlan: BillingPlan = {
  ...monthlyPlan,
  product_bid: 'bill-product-plan-yearly',
  product_code: 'creator-plan-yearly',
  billing_interval: 'year',
  credit_amount: 10000,
  price_amount: 1500000,
};

const dailyPlan: BillingPlan = {
  ...monthlyPlan,
  product_bid: 'bill-product-plan-daily',
  product_code: 'creator-plan-daily',
  billing_interval: 'day',
  billing_interval_count: 7,
  credit_amount: 21,
  price_amount: 390,
};

describe('formatBillingNumber (unified display rule)', () => {
  test('drops the decimal point for integer values', () => {
    expect(formatBillingNumber(1000, 'en-US')).toBe('1,000');
    expect(formatBillingNumber(0, 'en-US')).toBe('0');
    expect(formatBillingNumber(50000, 'en-US')).toBe('50,000');
  });

  test('strips trailing zeros and caps at two fraction digits', () => {
    expect(formatBillingNumber(50.5, 'en-US')).toBe('50.5');
    expect(formatBillingNumber(50.5, 'zh-CN')).toBe('50.5');
    expect(formatBillingNumber(50.567, 'en-US')).toBe('50.57');
    expect(formatBillingNumber(0.01, 'en-US')).toBe('0.01');
  });

  test('groups thousands for large numbers across locales', () => {
    expect(formatBillingNumber(1234567, 'en-US')).toBe('1,234,567');
    expect(formatBillingNumber(1234567, 'zh-CN')).toBe('1,234,567');
    expect(formatBillingNumber(1234567.89, 'en-US')).toBe('1,234,567.89');
  });

  test('falls back to zero for non-finite or nullish input', () => {
    expect(formatBillingNumber(NaN, 'en-US')).toBe('0');
    expect(formatBillingNumber(null, 'en-US')).toBe('0');
    expect(formatBillingNumber(undefined, 'en-US')).toBe('0');
    expect(formatBillingNumber(Number(''), 'en-US')).toBe('0');
  });

  test('renders narrow currency symbol when currency option is set', () => {
    expect(formatBillingNumber(99, 'zh-CN', { currency: 'CNY' })).toBe('¥99');
    expect(formatBillingNumber(0.01, 'zh-CN', { currency: 'CNY' })).toBe(
      '¥0.01',
    );
    expect(formatBillingNumber(99.5, 'zh-CN', { currency: 'CNY' })).toBe(
      '¥99.5',
    );
    expect(formatBillingNumber(99, 'en-US', { currency: 'CNY' })).toBe('¥99');
    expect(formatBillingNumber(99.5, 'en-US', { currency: 'USD' })).toBe(
      '$99.5',
    );
  });
});

describe('formatBillingCredits', () => {
  test('renders integers without decimals and groups thousands', () => {
    expect(formatBillingCredits(5, 'en-US')).toBe('5');
    expect(formatBillingCredits(10000, 'en-US')).toBe('10,000');
  });

  test('keeps meaningful decimals up to two places', () => {
    expect(formatBillingCredits(1.25, 'en-US')).toBe('1.25');
    expect(formatBillingCredits(1.256, 'en-US')).toBe('1.26');
    expect(formatBillingCredits(50.5, 'en-US')).toBe('50.5');
  });

  test('uses monthly credits copy for monthly plans', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.credits || '')}`;
    });

    expect(resolveBillingPlanCreditsLabel(t, monthlyPlan)).toBe(
      'module.billing.package.creditSummary.monthly:5',
    );
  });

  test('uses yearly credits copy for yearly plans', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.credits || '')}`;
    });

    expect(resolveBillingPlanCreditsLabel(t, yearlyPlan)).toBe(
      'module.billing.package.creditSummary.yearly:10,000',
    );
  });

  test('uses count-aware daily credits copy for daily plans', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.count || '')}:${String(options?.credits || '')}`;
    });

    expect(resolveBillingPlanCreditsLabel(t, dailyPlan)).toBe(
      'module.billing.package.creditSummary.days:7:21',
    );
  });
});

describe('formatBillingCreditBalance', () => {
  test('floors fractional balances to integers and keeps thousands separators', () => {
    expect(formatBillingCreditBalance(5)).toBe('5');
    expect(formatBillingCreditBalance(1.25)).toBe('1');
    expect(formatBillingCreditBalance(1.99)).toBe('1');
    expect(formatBillingCreditBalance(10000)).toBe('10,000');
    expect(formatBillingCreditBalance(32277.76)).toBe('32,277');
  });

  test('falls back to zero for non-finite or nullish input', () => {
    expect(formatBillingCreditBalance(NaN)).toBe('0');
    expect(formatBillingCreditBalance(Number.POSITIVE_INFINITY)).toBe('0');
  });
});

describe('formatBillingCreditAmount', () => {
  test('keeps thousands separators and meaningful decimals', () => {
    expect(formatBillingCreditAmount(5)).toBe('5');
    expect(formatBillingCreditAmount(10000)).toBe('10,000');
    expect(formatBillingCreditAmount(3200.88)).toBe('3,200.88');
  });
});

describe('formatBillingCreditDetail', () => {
  test('always renders exactly two fraction digits', () => {
    expect(formatBillingCreditDetail(0, 'en-US')).toBe('0.00');
    expect(formatBillingCreditDetail(100, 'en-US')).toBe('100.00');
    expect(formatBillingCreditDetail(1.5, 'en-US')).toBe('1.50');
    expect(formatBillingCreditDetail(23105, 'en-US')).toBe('23,105.00');
    expect(formatBillingCreditDetail(32277.76, 'en-US')).toBe('32,277.76');
  });

  test('rounds values with more than two fraction digits', () => {
    expect(formatBillingCreditDetail(1.999, 'en-US')).toBe('2.00');
    expect(formatBillingCreditDetail(0.005, 'en-US')).toBe('0.01');
  });

  test('keeps thousands separators across locales', () => {
    expect(formatBillingCreditDetail(1234567.89, 'en-US')).toBe('1,234,567.89');
    expect(formatBillingCreditDetail(1234567.89, 'zh-CN')).toBe('1,234,567.89');
  });

  test('falls back to zero for non-finite or nullish input', () => {
    expect(formatBillingCreditDetail(NaN, 'en-US')).toBe('0.00');
    expect(formatBillingCreditDetail(Number.POSITIVE_INFINITY, 'en-US')).toBe(
      '0.00',
    );
  });
});

describe('formatBillingPrice', () => {
  test('formats minor units to currency without trailing zeros', () => {
    expect(formatBillingPrice(1, 'CNY', 'zh-CN')).toBe('¥0.01');
    expect(formatBillingPrice(9900, 'CNY', 'zh-CN')).toBe('¥99');
    expect(formatBillingPrice(9950, 'CNY', 'zh-CN')).toBe('¥99.5');
    expect(formatBillingPrice(123456700, 'CNY', 'zh-CN')).toBe('¥1,234,567');
  });

  test('uses narrow symbol so CNY renders as ¥ across locales', () => {
    expect(formatBillingPrice(9900, 'CNY', 'en-US')).toBe('¥99');
  });

  test('supports other currencies', () => {
    expect(formatBillingPrice(9950, 'USD', 'en-US')).toBe('$99.5');
  });

  test('handles 0-decimal currency (JPY) without dividing by 100', () => {
    expect(formatBillingPrice(100, 'JPY', 'en-US')).toBe('¥100');
    expect(formatBillingPrice(100, 'JPY', 'zh-CN')).toBe('¥100');
    expect(formatBillingPrice(1234567, 'JPY', 'en-US')).toBe('¥1,234,567');
  });

  test('handles 3-decimal currency (KWD) preserving full precision', () => {
    expect(formatBillingPrice(1, 'KWD', 'en-US')).toBe('KWD 0.001');
    expect(formatBillingPrice(1000, 'KWD', 'en-US')).toBe('KWD 1');
    expect(formatBillingPrice(1234, 'KWD', 'en-US')).toBe('KWD 1.234');
  });

  test('falls back to zero for nullish input', () => {
    expect(formatBillingPrice(0, 'CNY', 'zh-CN')).toBe('¥0');
    expect(formatBillingPrice(null as unknown as number, 'CNY', 'zh-CN')).toBe(
      '¥0',
    );
  });
});

describe('billing interval formatters', () => {
  test('formats count-aware daily interval labels', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.count || '')}`;
    });

    expect(formatBillingPlanInterval(t, dailyPlan)).toBe(
      'module.billing.catalog.labels.everyDays:7',
    );
    expect(resolveBillingPlanValidityLabel(t, dailyPlan)).toBe(
      'module.billing.package.validity.days:7',
    );
  });
});

describe('resolveBillingLedgerReasonLabel', () => {
  const t = jest.fn((key: string) => key);

  function buildUsageItem(
    usageScene: BillingLedgerItem['metadata']['usage_scene'],
  ): BillingLedgerItem {
    return {
      ledger_bid: `ledger-${usageScene}`,
      wallet_bucket_bid: 'bucket-free',
      entry_type: 'consume',
      source_type: 'usage',
      source_bid: `usage-${usageScene}`,
      idempotency_key: `usage-${usageScene}-bucket-free`,
      amount: -1,
      balance_after: 99,
      expires_at: null,
      consumable_from: null,
      metadata: {
        usage_bid: `usage-${usageScene}`,
        usage_scene: usageScene,
        usage_type: 1101,
        course_name: `${usageScene} course`,
        user_identify: 'learner@example.com',
      },
      created_at: '2026-04-06T10:00:00Z',
    };
  }

  test('shows debug label and learner identifier for debug and preview usage', () => {
    expect(resolveBillingLedgerReasonLabel(t, buildUsageItem('debug'))).toBe(
      'module.billing.ledger.usageScene.debug - debug course - learner@example.com',
    );
    expect(resolveBillingLedgerReasonLabel(t, buildUsageItem('preview'))).toBe(
      'module.billing.ledger.usageScene.debug - preview course - learner@example.com',
    );
  });

  test('shows course name and learner identifier for production usage', () => {
    expect(
      resolveBillingLedgerReasonLabel(t, buildUsageItem('production')),
    ).toBe(
      'module.billing.ledger.usageScene.production - production course - learner@example.com',
    );
  });

  test('shows a TTS prefix for TTS usage entries', () => {
    expect(
      resolveBillingLedgerReasonLabel(t, {
        ...buildUsageItem('production'),
        metadata: {
          ...buildUsageItem('production').metadata,
          usage_type: 1102,
        },
      }),
    ).toBe(
      'module.billing.ledger.usageScene.tts - production course - learner@example.com',
    );
  });

  test('shows expire label for expired ledger entries', () => {
    expect(
      resolveBillingLedgerReasonLabel(t, {
        ledger_bid: 'ledger-expire',
        wallet_bucket_bid: 'bucket-expire',
        entry_type: 'expire',
        source_type: 'topup',
        source_bid: 'topup-expire',
        idempotency_key: 'expire:bucket-expire',
        amount: -3,
        balance_after: 0,
        expires_at: '2026-04-06T10:00:00Z',
        consumable_from: '2026-04-01T10:00:00Z',
        metadata: {},
        created_at: '2026-04-06T10:00:00Z',
      }),
    ).toBe('module.billing.ledger.entryType.expire');
  });
});

describe('resolveBillingLedgerUsageType', () => {
  test('maps backend numeric usage_type codes', () => {
    expect(resolveBillingLedgerUsageType({ usage_type: 1102 })).toBe('tts');
    expect(resolveBillingLedgerUsageType({ usage_type: 1101 })).toBe('llm');
  });

  test('falls back to metric breakdown when usage_type is missing', () => {
    expect(
      resolveBillingLedgerUsageType({
        metric_breakdown: [
          {
            billing_metric: 'tts_request_count',
            raw_amount: 1,
            unit_size: 1,
            credits_per_unit: 0.01,
            rounding_mode: 'ceil',
            consumed_credits: 0.01,
          },
        ],
      }),
    ).toBe('tts');
  });
});

describe('parseBillingDateValue', () => {
  test('treats offsetless legacy billing instants as app-local +08:00 values', () => {
    expect(parseBillingDateValue('2026-04-14T07:32:00')?.toISOString()).toBe(
      '2026-04-13T23:32:00.000Z',
    );
  });

  test('keeps offset-aware billing instants unchanged', () => {
    expect(
      parseBillingDateValue('2026-04-14T07:32:00+08:00')?.toISOString(),
    ).toBe('2026-04-13T23:32:00.000Z');
  });
});

describe('extractBillingPingxxQrCode', () => {
  function buildCheckoutResult(
    credential: Record<string, string>,
  ): BillingCheckoutResult {
    return {
      bill_order_bid: 'bill-order-native',
      payment_mode: 'one_time',
      payment_payload: { credential },
      provider: 'alipay',
      status: 'pending',
    };
  }

  test('extracts an Alipay native QR credential', () => {
    expect(
      extractBillingPingxxQrCode(
        buildCheckoutResult({ alipay_qr: 'https://qr.example/alipay' }),
        'alipay_qr',
      ),
    ).toEqual({
      channel: 'alipay_qr',
      url: 'https://qr.example/alipay',
    });
  });

  test('extracts a WeChat Pay native QR credential', () => {
    expect(
      extractBillingPingxxQrCode(
        buildCheckoutResult({ wx_pub_qr: 'weixin://wxpay/bizpayurl' }),
        'wx_pub_qr',
      ),
    ).toEqual({
      channel: 'wx_pub_qr',
      url: 'weixin://wxpay/bizpayurl',
    });
  });

  test('returns null when requested QR credential is missing or empty', () => {
    expect(
      extractBillingPingxxQrCode(buildCheckoutResult({}), 'alipay_qr'),
    ).toBeNull();
    expect(
      extractBillingPingxxQrCode(
        buildCheckoutResult({ alipay_qr: '' }),
        'alipay_qr',
      ),
    ).toBeNull();
  });
});
