import {
  formatBillingCredits,
  formatBillingPlanInterval,
  getBillingCreditPrecision,
  parseBillingDateValue,
  resolveBillingLedgerReasonLabel,
  resolveBillingPlanCreditsLabel,
  resolveBillingPlanValidityLabel,
  setBillingCreditPrecision,
} from '@/lib/billing';
import type { BillingLedgerItem, BillingPlan } from '@/types/billing';

const monthlyPlan: BillingPlan = {
  product_bid: 'billing-product-plan-monthly',
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
  product_bid: 'billing-product-plan-yearly',
  product_code: 'creator-plan-yearly',
  billing_interval: 'year',
  credit_amount: 10000,
  price_amount: 1500000,
};

const dailyPlan: BillingPlan = {
  ...monthlyPlan,
  product_bid: 'billing-product-plan-daily',
  product_code: 'creator-plan-daily',
  billing_interval: 'day',
  billing_interval_count: 7,
  credit_amount: 21,
  price_amount: 390,
};

describe('resolveBillingPlanCreditsLabel', () => {
  afterEach(() => {
    setBillingCreditPrecision();
  });

  test('formats credits with fixed two-decimal precision by default', () => {
    expect(getBillingCreditPrecision()).toBe(2);
    expect(formatBillingCredits(5, 'en-US')).toBe('5.00');
    expect(formatBillingCredits(1.25, 'en-US')).toBe('1.25');
    expect(formatBillingCredits(10000, 'en-US')).toBe('10,000.00');
  });

  test('formats credits with runtime-configured precision', () => {
    setBillingCreditPrecision(2);
    expect(formatBillingCredits(1.256, 'en-US')).toBe('1.26');
    expect(formatBillingCredits(10000, 'en-US')).toBe('10,000.00');
  });

  test('uses monthly credits copy for monthly plans', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.credits || '')}`;
    });

    expect(resolveBillingPlanCreditsLabel(t, monthlyPlan, 'zh-CN')).toBe(
      'module.billing.package.creditSummary.monthly:5.00',
    );
  });

  test('uses yearly credits copy for yearly plans', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.credits || '')}`;
    });

    expect(resolveBillingPlanCreditsLabel(t, yearlyPlan, 'en-US')).toBe(
      'module.billing.package.creditSummary.yearly:10,000.00',
    );
  });

  test('uses count-aware daily credits copy for daily plans', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.count || '')}:${String(options?.credits || '')}`;
    });

    expect(resolveBillingPlanCreditsLabel(t, dailyPlan, 'en-US')).toBe(
      'module.billing.package.creditSummary.days:7:21.00',
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
        course_name: `${usageScene} course`,
        user_identify: 'learner@example.com',
      },
      created_at: '2026-04-06T10:00:00Z',
    };
  }

  test('shows course name for debug and preview usage', () => {
    expect(resolveBillingLedgerReasonLabel(t, buildUsageItem('debug'))).toBe(
      'module.billing.ledger.usageScene.debug - debug course',
    );
    expect(resolveBillingLedgerReasonLabel(t, buildUsageItem('preview'))).toBe(
      'module.billing.ledger.usageScene.preview - preview course',
    );
  });

  test('shows course name and learner identifier for production usage', () => {
    expect(
      resolveBillingLedgerReasonLabel(t, buildUsageItem('production')),
    ).toBe(
      'module.billing.ledger.usageScene.production - production course - learner@example.com',
    );
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
