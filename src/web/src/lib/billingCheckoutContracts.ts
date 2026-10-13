/** Server-owned checkout operations and isolated compatibility with old catalogs. */
import type { PaymentOption } from '@/types/payment';
import type {
  BillingCheckoutOperation,
  BillingPlan,
  BillingProvider,
  BillingSubscription,
  BillingSubscriptionCheckoutAction,
} from '@/types/billing';

type ActionTone = 'primary' | 'current' | 'muted';
const SAME_PLAN_RENEWAL_LIMIT_TOLERANCE_MS = 24 * 60 * 60 * 1000;
type CheckoutContext = {
  plan: BillingPlan;
  orderedPlans: BillingPlan[];
  currentPlan: BillingPlan | null;
  currentSubscription: BillingSubscription | null;
  hasActiveSubscription: boolean;
  isTrialCurrentPlan: boolean;
  paymentOptions?: PaymentOption[];
  stripeAvailable: boolean;
  pingxxAvailable: boolean;
  alipayAvailable: boolean;
  wechatpayAvailable: boolean;
};
export type PlanCheckoutPresentation = {
  action?: BillingSubscriptionCheckoutAction;
  actionProvider: BillingProvider | null;
  actionLabelKey: string;
  actionDisabled: boolean;
  actionTone: ActionTone;
  actionTooltipKey?: string;
};

export function resolvePlanCheckoutPresentation(
  context: CheckoutContext & { operation?: BillingCheckoutOperation },
): PlanCheckoutPresentation {
  const { operation, paymentOptions } = context;
  if (operation) {
    const selected = paymentOptions?.find(
      option => option.id === operation.option_ids[0],
    );
    const actionProvider =
      operation.available && selected ? selected.provider : null;
    return {
      action: operation.action === 'subscribe' ? undefined : operation.action,
      actionProvider,
      actionLabelKey: operation.label_key,
      actionDisabled: !actionProvider,
      actionTone: operation.tone,
      actionTooltipKey: operation.tooltip_key || undefined,
    };
  }
  return resolveLegacyPlanCheckout(context);
}

/** Preserve mixed-version behavior; new catalogs never derive eligibility here. */
function resolveLegacyPlanCheckout({
  plan,
  orderedPlans,
  currentPlan,
  currentSubscription,
  hasActiveSubscription,
  isTrialCurrentPlan,
  paymentOptions,
  stripeAvailable,
  pingxxAvailable,
  alipayAvailable,
  wechatpayAvailable,
}: CheckoutContext): PlanCheckoutPresentation {
  const provider = resolveCheckoutProvider(
    stripeAvailable,
    pingxxAvailable,
    alipayAvailable,
    wechatpayAvailable,
    paymentOptions,
  );
  const currentTier = planTierIn(orderedPlans, currentPlan);
  const currentProvider = currentSubscription?.billing_provider || null;
  const pendingPreorderProductBid =
    currentSubscription?.next_product_bid || null;
  const hasPendingPreorder = Boolean(
    hasActiveSubscription && pendingPreorderProductBid,
  );
  const immediateUpgradeProvider = resolveImmediateUpgradeProvider(
    currentProvider,
    provider,
    {
      isTrialCurrentPlan,
      hasPendingPreorder,
    },
  );

  const isCurrentPlan = currentPlan?.product_bid === plan.product_bid;
  const targetTier = planTierIn(orderedPlans, plan);
  const hasComparableTier =
    Number.isFinite(currentTier) && Number.isFinite(targetTier);
  const isHigherTier =
    hasActiveSubscription && (!hasComparableTier || targetTier > currentTier);
  const isSameOrLowerTier =
    hasActiveSubscription && hasComparableTier && targetTier <= currentTier;
  const isPendingPreorderTarget =
    pendingPreorderProductBid === plan.product_bid;
  const samePlanRenewalLimitReached =
    isCurrentPlan && isSamePlanRenewalLimitReached(currentSubscription, plan);
  let action: BillingSubscriptionCheckoutAction | undefined;
  let actionProvider = hasActiveSubscription ? null : provider;
  let actionLabelKey = 'module.billing.package.actions.subscribeNow';
  let actionDisabled = !actionProvider;
  let actionTone: ActionTone = 'primary';
  let actionTooltipKey: string | undefined;

  if (hasActiveSubscription) {
    if (hasPendingPreorder) {
      if (isPendingPreorderTarget) {
        actionLabelKey = 'module.billing.package.actions.preorderScheduled';
        actionDisabled = true;
        actionTone = 'muted';
        actionTooltipKey =
          'module.billing.package.actions.preorderLockedTooltip';
      } else if (isHigherTier) {
        action = 'upgrade_immediate';
        actionLabelKey = 'module.billing.package.actions.upgradeNow';
        if (
          isProviderAvailable(
            immediateUpgradeProvider,
            stripeAvailable,
            pingxxAvailable,
            alipayAvailable,
            wechatpayAvailable,
            paymentOptions,
          )
        ) {
          actionProvider = immediateUpgradeProvider;
        }
        actionDisabled = !actionProvider;
      } else {
        actionLabelKey = isCurrentPlan
          ? 'module.billing.package.actions.currentSubscription'
          : 'module.billing.package.actions.preorderLocked';
        actionDisabled = true;
        actionTone = isCurrentPlan ? 'current' : 'muted';
        actionTooltipKey = isCurrentPlan
          ? undefined
          : 'module.billing.package.actions.preorderLockedTooltip';
      }
    } else if (isSameOrLowerTier) {
      const canPreorder =
        isSelfManagedPreorderProvider(currentProvider, paymentOptions) &&
        isProviderAvailable(
          currentProvider,
          stripeAvailable,
          pingxxAvailable,
          alipayAvailable,
          wechatpayAvailable,
          paymentOptions,
        );
      if (samePlanRenewalLimitReached) {
        action = 'preorder';
        actionProvider = null;
        actionLabelKey = 'module.billing.package.actions.preorderScheduled';
        actionDisabled = true;
        actionTone = 'muted';
        actionTooltipKey =
          'module.billing.package.actions.preorderLockedTooltip';
      } else {
        action = 'preorder';
        actionProvider = canPreorder ? currentProvider : null;
        actionLabelKey = isCurrentPlan
          ? 'module.billing.package.actions.preorderRenewal'
          : 'module.billing.package.actions.preorderDowngrade';
        actionDisabled = !canPreorder;
        actionTone = canPreorder ? 'primary' : 'muted';
        actionTooltipKey = canPreorder
          ? undefined
          : 'module.billing.package.actions.preorderProviderUnsupportedTooltip';
      }
    } else {
      action = 'upgrade_immediate';
      actionLabelKey = 'module.billing.package.actions.upgradeNow';
      if (
        isProviderAvailable(
          immediateUpgradeProvider,
          stripeAvailable,
          pingxxAvailable,
          alipayAvailable,
          wechatpayAvailable,
          paymentOptions,
        )
      ) {
        actionProvider = immediateUpgradeProvider;
      }
      actionDisabled = !actionProvider;
    }
  }

  return {
    action,
    actionProvider,
    actionLabelKey,
    actionDisabled,
    actionTone,
    actionTooltipKey,
  };
}

function planRankIn(ordered: BillingPlan[], productBid: string | null): number {
  if (!productBid) return -1;
  return ordered.findIndex(plan => plan.product_bid === productBid);
}

function planTierIn(ordered: BillingPlan[], plan: BillingPlan | null): number {
  if (!plan) return Number.NaN;
  if (typeof plan.plan_tier === 'number') return plan.plan_tier;
  const rank = planRankIn(ordered, plan.product_bid);
  return rank >= 0 ? rank : Number.NaN;
}

function resolveCheckoutProvider(
  stripeAvailable: boolean,
  pingxxAvailable: boolean,
  alipayAvailable: boolean,
  wechatpayAvailable: boolean,
  paymentOptions?: PaymentOption[],
): BillingProvider | null {
  if (paymentOptions) return paymentOptions[0]?.provider || null;
  if (stripeAvailable) return 'stripe';
  if (alipayAvailable) return 'alipay';
  if (wechatpayAvailable) return 'wechatpay';
  if (pingxxAvailable) return 'pingxx';
  return null;
}

function isProviderAvailable(
  provider: BillingProvider | null | undefined,
  stripeAvailable: boolean,
  pingxxAvailable: boolean,
  alipayAvailable: boolean,
  wechatpayAvailable: boolean,
  paymentOptions?: PaymentOption[],
): provider is BillingProvider {
  if (paymentOptions)
    return paymentOptions.some(option => option.provider === provider);
  if (provider === 'stripe') return stripeAvailable;
  if (provider === 'pingxx') return pingxxAvailable;
  if (provider === 'alipay') return alipayAvailable;
  if (provider === 'wechatpay') return wechatpayAvailable;
  return false;
}

function isSelfManagedPreorderProvider(
  provider: BillingProvider | null | undefined,
  paymentOptions?: PaymentOption[],
): provider is BillingProvider {
  if (paymentOptions)
    return paymentOptions.some(
      option =>
        option.provider === provider &&
        option.billing_mode === 'platform_managed',
    );
  return (
    provider === 'pingxx' || provider === 'alipay' || provider === 'wechatpay'
  );
}

function resolveImmediateUpgradeProvider(
  currentProvider: BillingProvider | null,
  fallbackProvider: BillingProvider | null,
  options: {
    isTrialCurrentPlan: boolean;
    hasPendingPreorder: boolean;
  },
): BillingProvider | null {
  if (options.isTrialCurrentPlan) return fallbackProvider;
  if (currentProvider === 'manual' && !options.hasPendingPreorder) {
    return fallbackProvider;
  }
  return currentProvider;
}

function endOfLocalDay(value: Date): Date {
  const end = new Date(value.getTime());
  end.setHours(23, 59, 59, 0);
  return end;
}

function calculateSelfManagedCycleEndFromNow(
  plan: BillingPlan,
  now = new Date(),
): Date | null {
  const intervalCount = Math.max(plan.billing_interval_count || 0, 0);
  if (intervalCount <= 0) return null;

  if (plan.billing_interval === 'day') {
    return endOfLocalDay(
      new Date(now.getTime() + (intervalCount - 1) * 24 * 60 * 60 * 1000),
    );
  }

  if (plan.billing_interval === 'month') {
    return endOfLocalDay(
      new Date(now.getTime() + (30 * intervalCount - 1) * 24 * 60 * 60 * 1000),
    );
  }

  if (plan.billing_interval === 'year') {
    const end = new Date(now.getTime());
    end.setFullYear(end.getFullYear() + intervalCount);
    return endOfLocalDay(end);
  }

  return null;
}

function isSamePlanRenewalLimitReached(
  currentSubscription: BillingSubscription | null,
  plan: BillingPlan,
): boolean {
  const currentPeriodEndAt = currentSubscription?.current_period_end_at;
  if (!currentPeriodEndAt) return false;

  const currentPeriodEnd = new Date(currentPeriodEndAt);
  if (Number.isNaN(currentPeriodEnd.getTime())) return false;

  const maxSinglePrepaidEnd = calculateSelfManagedCycleEndFromNow(plan);
  if (!maxSinglePrepaidEnd) return false;

  return (
    currentPeriodEnd.getTime() - maxSinglePrepaidEnd.getTime() >
    SAME_PLAN_RENEWAL_LIMIT_TOLERANCE_MS
  );
}
