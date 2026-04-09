import { resolveBillingPlanCreditsLabel } from '@/lib/billing';
import type { BillingPlan } from '@/types/billing';

const monthlyPlan: BillingPlan = {
  product_bid: 'billing-product-plan-monthly',
  creator_bid: 'creator-bid',
  product_type: 'plan',
  code: 'creator-plan-monthly',
  billing_provider: 'stripe',
  display_name: 'module.billing.catalog.plans.creatorMonthly.title',
  description: 'module.billing.catalog.plans.creatorMonthly.description',
  currency: 'CNY',
  price_amount: 990,
  credit_amount: 5,
  billing_interval: 'month',
  interval_count: 1,
  status: 'active',
  status_badge_key: null,
  metadata: {},
  created_at: '2026-04-09T00:00:00Z',
  updated_at: '2026-04-09T00:00:00Z',
};

const yearlyPlan: BillingPlan = {
  ...monthlyPlan,
  product_bid: 'billing-product-plan-yearly',
  code: 'creator-plan-yearly',
  billing_interval: 'year',
  credit_amount: 10000,
  price_amount: 1500000,
};

describe('resolveBillingPlanCreditsLabel', () => {
  test('uses monthly credits copy for monthly plans', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.credits || '')}`;
    });

    expect(resolveBillingPlanCreditsLabel(t, monthlyPlan, 'zh-CN')).toBe(
      'module.billing.package.creditSummary.monthly:5',
    );
  });

  test('uses yearly credits copy for yearly plans', () => {
    const t = jest.fn((key: string, options?: Record<string, unknown>) => {
      return `${key}:${String(options?.credits || '')}`;
    });

    expect(resolveBillingPlanCreditsLabel(t, yearlyPlan, 'en-US')).toBe(
      'module.billing.package.creditSummary.yearly:10,000',
    );
  });
});
