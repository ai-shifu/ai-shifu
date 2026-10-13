import { resolvePlanCheckoutPresentation } from './billingCheckoutContracts';
import type { BillingPlan, BillingCheckoutOperation } from '@/types/billing';
import type { PaymentOption } from '@/types/payment';

const plan: BillingPlan = {
  product_bid: 'plan',
  product_code: 'plan',
  product_type: 'plan',
  display_name: 'Plan',
  description: '',
  billing_interval: 'month',
  billing_interval_count: 1,
  currency: 'CNY',
  price_amount: 990,
  credit_amount: 100,
  auto_renew_enabled: true,
};
const option: PaymentOption = {
  id: 'catalog:hosted',
  provider: 'new-catalog',
  channel: 'hosted',
  method: 'hosted',
  scene: 'hosted',
  action: 'redirect',
  billing_mode: 'provider_managed',
  label_key: 'catalog',
  poll_provider: false,
  requires_open_id: false,
};
const context = {
  plan,
  orderedPlans: [plan],
  currentPlan: plan,
  currentSubscription: null,
  hasActiveSubscription: true,
  isTrialCurrentPlan: false,
  stripeAvailable: true,
  pingxxAvailable: true,
  alipayAvailable: true,
  wechatpayAvailable: true,
  paymentOptions: [option],
};
const operation: BillingCheckoutOperation = {
  action: 'upgrade_immediate',
  available: true,
  option_ids: [option.id],
  label_key: 'module.billing.package.actions.upgradeNow',
  tone: 'primary',
};

test('uses the authorized operation even when legacy client eligibility would disagree', () => {
  expect(resolvePlanCheckoutPresentation({ ...context, operation })).toEqual({
    action: 'upgrade_immediate',
    actionProvider: 'new-catalog',
    actionLabelKey: operation.label_key,
    actionDisabled: false,
    actionTone: 'primary',
    actionTooltipKey: undefined,
  });
});

test.each([false, true])(
  'never enables an unavailable or missing server-selected option: %s',
  available => {
    const result = resolvePlanCheckoutPresentation({
      ...context,
      operation: {
        ...operation,
        available,
        option_ids: available ? ['unavailable:hosted'] : [option.id],
        tone: 'muted',
      },
    });
    expect(result.actionDisabled).toBe(true);
    expect(result.actionProvider).toBeNull();
  },
);

test('retains old catalog compatibility while new catalogs use server authority', () => {
  const legacy = resolvePlanCheckoutPresentation({
    ...context,
    hasActiveSubscription: false,
  });
  expect(legacy.actionProvider).toBe('new-catalog');
  expect(legacy.action).toBeUndefined();
  expect(
    resolvePlanCheckoutPresentation({
      ...context,
      operation: { ...operation, action: 'preorder', available: false },
    }).actionDisabled,
  ).toBe(true);
});
