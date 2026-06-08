import { Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  formatBillingCreditAmount,
  formatBillingPrice,
  getBillingProductCampaignBonusCredits,
  hasBillingProductBonusCampaign,
  formatBillingPlanInterval,
  hasBillingProductDiscountCampaign,
  resolveBillingProductPayableAmount,
  resolveBillingProductTitle,
  resolveBillingProductDescription,
} from '@/lib/billing';
import type {
  BillingPlan,
  BillingProvider,
  BillingSubscription,
  BillingSubscriptionCheckoutAction,
  BillingTrialOffer,
} from '@/types/billing';
import { cn } from '@/lib/utils';
import {
  getFreeFeatureData,
  getPlanFeatureData,
  getPlanScaleKeys,
} from './BillingOverviewCards';
import styles from './BillingPlanComparisonTable.module.scss';

// Language-neutral typographic enumerators that anchor each metric row label
// to the matching footnote item. Not user-facing copy, so they stay out of
// i18n.
const ROW_ENUM_LEARNER = '①';
const ROW_ENUM_VALIDITY = '②';
const SAME_PLAN_RENEWAL_LIMIT_TOLERANCE_MS = 24 * 60 * 60 * 1000;

type FeatureRow = {
  i18nKey: string;
  unlockIndex: number;
};

function buildFeatureRows(
  trialFeatureKeys: string[],
  paidPlans: BillingPlan[],
): FeatureRow[] {
  const seen = new Map<string, number>();
  trialFeatureKeys.forEach(key => {
    if (!seen.has(key)) {
      seen.set(key, -1);
    }
  });
  paidPlans.forEach((plan, idx) => {
    const items = getPlanFeatureData(plan).items;
    items.forEach(key => {
      if (!seen.has(key)) {
        seen.set(key, idx);
      }
    });
  });
  return Array.from(seen.entries())
    .map(([i18nKey, unlockIndex]) => ({ i18nKey, unlockIndex }))
    .sort((a, b) => a.unlockIndex - b.unlockIndex);
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

function shortenIntervalLabel(label: string): string {
  if (!label) return '';
  return label
    .replace(/^每\s*/, '')
    .replace(/^per\s*/i, '')
    .trim();
}

function resolveCheckoutProvider(
  stripeAvailable: boolean,
  pingxxAvailable: boolean,
  alipayAvailable: boolean,
  wechatpayAvailable: boolean,
): BillingProvider | null {
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
): provider is BillingProvider {
  if (provider === 'stripe') return stripeAvailable;
  if (provider === 'pingxx') return pingxxAvailable;
  if (provider === 'alipay') return alipayAvailable;
  if (provider === 'wechatpay') return wechatpayAvailable;
  return false;
}

function isSelfManagedPreorderProvider(
  provider: BillingProvider | null | undefined,
): provider is BillingProvider {
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

type ActionTone = 'primary' | 'current' | 'muted';

type ColumnAction = {
  label: string;
  loading: boolean;
  disabled: boolean;
  tone: ActionTone;
  tooltip?: string;
  onClick?: () => void;
  testId: string;
};

const TONE_VARIANT: Record<ActionTone, 'default' | 'secondary'> = {
  primary: 'default',
  current: 'default',
  muted: 'secondary',
};

type ColumnDescriptor = {
  key: string;
  testId: string;
  title: string;
  description: string;
  badgeLabel?: string;
  campaignLabel?: string;
  originalPriceLabel?: string;
  priceLabel: string;
  periodLabel: string;
  creditAmount: string;
  featured: boolean;
  validityShort: string;
  studentLabel?: string;
  features: boolean[];
  action: ColumnAction;
};

type BillingTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

function resolvePlanValidityShort(
  t: BillingTranslator,
  plan: BillingPlan,
): string {
  const intervalCount = Math.max(plan.billing_interval_count || 0, 1);
  if (plan.billing_interval === 'month') {
    return t('module.billing.package.validityShort.monthly', {
      count: intervalCount,
    });
  }
  if (plan.billing_interval === 'year') {
    return t('module.billing.package.validityShort.yearly', {
      count: intervalCount,
    });
  }
  return '';
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

export type BillingPlanComparisonTableProps = {
  trialOffer: BillingTrialOffer | null | undefined;
  paidPlans: BillingPlan[];
  orderedPlans: BillingPlan[];
  currentPlan: BillingPlan | null;
  currentSubscription: BillingSubscription | null;
  hasActiveSubscription: boolean;
  isTrialCurrentPlan: boolean;
  renderFreeColumn: boolean;
  checkoutLoadingKey: string;
  stripeAvailable: boolean;
  pingxxAvailable: boolean;
  alipayAvailable: boolean;
  wechatpayAvailable: boolean;
  onSelectPlanCheckout: (
    plan: BillingPlan,
    provider: BillingProvider,
    action?: BillingSubscriptionCheckoutAction,
  ) => void;
};

export function BillingPlanComparisonTable({
  trialOffer,
  paidPlans,
  orderedPlans,
  currentPlan,
  currentSubscription,
  hasActiveSubscription,
  isTrialCurrentPlan,
  renderFreeColumn,
  checkoutLoadingKey,
  stripeAvailable,
  pingxxAvailable,
  alipayAvailable,
  wechatpayAvailable,
  onSelectPlanCheckout,
}: BillingPlanComparisonTableProps) {
  const { t, i18n } = useTranslation();
  const processingLabel = t('module.billing.catalog.actions.processing');
  const emptyValue = t('module.billing.package.table.emptyValue');
  const trialFeatureKeys = getFreeFeatureData().items;
  const featureRows = buildFeatureRows(trialFeatureKeys, paidPlans);
  const provider = resolveCheckoutProvider(
    stripeAvailable,
    pingxxAvailable,
    alipayAvailable,
    wechatpayAvailable,
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

  const columns: ColumnDescriptor[] = [];

  if (renderFreeColumn) {
    const trialFeatureSet = new Set(trialFeatureKeys);
    const trialScale = getPlanScaleKeys(
      trialOffer?.product_code || 'creator-plan-trial',
    );
    columns.push({
      key: 'free',
      testId: 'billing-plan-card-free',
      title: resolveBillingProductTitle(
        t,
        trialOffer,
        t('module.billing.package.free.title'),
      ),
      description: resolveBillingProductDescription(
        t,
        trialOffer,
        t('module.billing.package.free.description'),
      ),
      priceLabel:
        trialOffer && trialOffer.currency
          ? formatBillingPrice(
              trialOffer.price_amount,
              trialOffer.currency,
              i18n.language,
            )
          : emptyValue,
      periodLabel: '',
      creditAmount: t('module.billing.package.topup.creditLabel', {
        credits: formatBillingCreditAmount(trialOffer?.credit_amount || 0),
      }),
      featured: isTrialCurrentPlan || !hasActiveSubscription,
      validityShort: trialOffer
        ? t('module.billing.package.validityShort.free', {
            days: trialOffer.valid_days,
          })
        : emptyValue,
      studentLabel: trialScale ? t(trialScale.students) : undefined,
      features: featureRows.map(
        row => row.unlockIndex === -1 || trialFeatureSet.has(row.i18nKey),
      ),
      action: {
        label: t(
          !hasActiveSubscription || isTrialCurrentPlan
            ? 'module.billing.package.actions.currentUsing'
            : 'module.billing.package.actions.freeTrial',
        ),
        loading: false,
        disabled: true,
        tone:
          !hasActiveSubscription || isTrialCurrentPlan ? 'current' : 'muted',
        tooltip: !hasActiveSubscription
          ? t('module.billing.package.actions.nonMemberTooltip')
          : undefined,
        testId: 'billing-plan-card-free-action',
      },
    });
  }

  paidPlans.forEach((plan, idx) => {
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
          isSelfManagedPreorderProvider(currentProvider) &&
          isProviderAvailable(
            currentProvider,
            stripeAvailable,
            pingxxAvailable,
            alipayAvailable,
            wechatpayAvailable,
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
          )
        ) {
          actionProvider = immediateUpgradeProvider;
        }
        actionDisabled = !actionProvider;
      }
    }

    const checkoutKey = actionProvider
      ? `plan:${actionProvider}:${plan.product_bid}:${action || 'subscription'}`
      : null;
    const planScale = getPlanScaleKeys(plan.product_code);
    const badgeKey = plan.status_badge_key;
    const showCurrentSubscriptionState =
      hasActiveSubscription && !hasPendingPreorder && !action && isCurrentPlan;

    const hasDiscountCampaign = hasBillingProductDiscountCampaign(plan);
    const hasBonusCampaign = hasBillingProductBonusCampaign(plan);
    const bonusCreditAmount = getBillingProductCampaignBonusCredits(plan);
    const payableAmount = resolveBillingProductPayableAmount(plan);

    columns.push({
      key: plan.product_bid,
      testId: `billing-plan-card-${plan.product_bid}`,
      title: resolveBillingProductTitle(t, plan),
      description: resolveBillingProductDescription(t, plan),
      badgeLabel: badgeKey ? t(badgeKey) : undefined,
      campaignLabel: hasDiscountCampaign
        ? t('module.billing.package.campaign.discountBadge')
        : hasBonusCampaign
          ? t('module.billing.package.campaign.bonusBadge', {
              credits: formatBillingCreditAmount(bonusCreditAmount),
            })
          : undefined,
      originalPriceLabel: hasDiscountCampaign
        ? formatBillingPrice(plan.price_amount, plan.currency, i18n.language)
        : undefined,
      priceLabel: formatBillingPrice(
        payableAmount,
        plan.currency,
        i18n.language,
      ),
      periodLabel: shortenIntervalLabel(formatBillingPlanInterval(t, plan)),
      creditAmount: t('module.billing.package.topup.creditLabel', {
        credits: formatBillingCreditAmount(plan.credit_amount),
      }),
      featured: isCurrentPlan,
      validityShort: resolvePlanValidityShort(t, plan),
      studentLabel: planScale ? t(planScale.students) : undefined,
      features: featureRows.map(
        row => row.unlockIndex === -1 || idx >= row.unlockIndex,
      ),
      action: {
        label: t(
          showCurrentSubscriptionState
            ? 'module.billing.package.actions.currentSubscription'
            : actionLabelKey,
        ),
        loading: checkoutKey !== null && checkoutLoadingKey === checkoutKey,
        disabled: actionDisabled || showCurrentSubscriptionState,
        tone: showCurrentSubscriptionState ? 'current' : actionTone,
        tooltip: actionTooltipKey ? t(actionTooltipKey) : undefined,
        onClick: () =>
          actionProvider && onSelectPlanCheckout(plan, actionProvider, action),
        testId: `billing-plan-card-${plan.product_bid}-action`,
      },
    });
  });

  if (columns.length === 0) {
    return null;
  }

  const renderColumnAction = (col: ColumnDescriptor) => {
    const actionButton = (
      <Button
        className={cn(
          styles.columnAction,
          col.action.tone === 'current' && 'disabled:opacity-100',
        )}
        data-testid={col.action.testId}
        disabled={col.action.disabled || col.action.loading}
        onClick={col.action.onClick}
        type='button'
        variant={TONE_VARIANT[col.action.tone]}
      >
        {col.action.loading ? processingLabel : col.action.label}
      </Button>
    );

    if (!col.action.tooltip) {
      return actionButton;
    }

    return (
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className={styles.columnActionWrap}
              data-testid={`${col.action.testId}-trigger`}
              tabIndex={0}
            >
              {actionButton}
            </span>
          </TooltipTrigger>
          <TooltipContent>{col.action.tooltip}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  return (
    <div
      className={styles.tableWrapper}
      data-testid='billing-plan-comparison-table'
    >
      <table className={styles.table}>
        <colgroup>
          {columns.map(col => (
            <col
              key={col.key}
              style={{ width: `${100 / columns.length}%` }}
            />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map(col => (
              <th
                key={`${col.key}-title`}
                className={cn(
                  styles.columnHead,
                  styles.columnTitleHead,
                  col.featured && styles.featuredColumnTitle,
                )}
                data-testid={col.testId}
                data-featured={col.featured ? 'true' : 'false'}
                scope='col'
              >
                <div className={styles.columnTitleRow}>
                  <span className={styles.columnTitle}>{col.title}</span>
                  {col.badgeLabel ? (
                    <span className={styles.columnBadge}>
                      <Star className={styles.columnBadgeIcon} />
                      {col.badgeLabel}
                    </span>
                  ) : null}
                </div>
              </th>
            ))}
          </tr>
          <tr>
            {columns.map(col => (
              <td
                key={`${col.key}-price`}
                className={cn(
                  styles.columnHead,
                  styles.columnPriceHead,
                  col.featured && styles.featuredColumnPrice,
                )}
              >
                <div
                  className={styles.columnPriceSummary}
                  data-testid={`${col.testId}-price-summary`}
                >
                  <div className={styles.columnPrice}>
                    {col.originalPriceLabel ? (
                      <div className={styles.columnOriginalPrice}>
                        {col.originalPriceLabel}
                      </div>
                    ) : null}
                    <div>
                      {col.periodLabel
                        ? `${col.priceLabel} / ${col.periodLabel}`
                        : col.priceLabel}
                    </div>
                    {col.campaignLabel ? (
                      <div className={styles.columnCampaignLabel}>
                        {col.campaignLabel}
                      </div>
                    ) : null}
                  </div>
                  <div className={styles.columnCreditAmount}>
                    {col.creditAmount}
                  </div>
                </div>
              </td>
            ))}
          </tr>
          <tr>
            {columns.map(col => (
              <td
                key={`${col.key}-action`}
                className={cn(
                  styles.columnHead,
                  styles.columnActionHead,
                  col.featured && styles.featuredColumnAction,
                )}
              >
                {renderColumnAction(col)}
              </td>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className={styles.scenarioRow}>
            {columns.map(col => (
              <td
                key={col.key}
                className={cn(col.featured && styles.featuredColumn)}
              >
                <div className={styles.scenarioText}>{col.description}</div>
              </td>
            ))}
          </tr>
          <tr className={styles.dataRow}>
            {columns.map(col => (
              <td
                key={col.key}
                className={cn(col.featured && styles.featuredColumn)}
              >
                <div className={styles.cellLabel}>
                  {t('module.billing.package.table.studentsRowLabel')}
                  <span className='ml-1 font-medium'>{ROW_ENUM_LEARNER}</span>
                </div>
                <div className={styles.cellValue}>
                  {col.studentLabel || emptyValue}
                </div>
              </td>
            ))}
          </tr>
          <tr className={styles.dataRow}>
            {columns.map(col => (
              <td
                key={col.key}
                className={cn(col.featured && styles.featuredColumn)}
              >
                <div className={styles.cellLabel}>
                  {t('module.billing.package.table.validityRowLabel')}
                  <span className='ml-1 font-medium'>{ROW_ENUM_VALIDITY}</span>
                </div>
                <div className={styles.cellValue}>
                  <span>{col.validityShort || emptyValue}</span>
                </div>
              </td>
            ))}
          </tr>
          <tr className={styles.featureColumnRow}>
            {columns.map(col => (
              <td
                key={col.key}
                className={cn(col.featured && styles.featuredColumn)}
              >
                <div className={styles.cellLabel}>
                  {t('module.billing.package.table.featuresRowLabel')}
                </div>
                <ul className={styles.featureColumnList}>
                  {featureRows.map((row, rowIdx) =>
                    col.features[rowIdx] ? (
                      <li
                        key={row.i18nKey}
                        className={styles.featureColumnItem}
                      >
                        <span className={styles.featureColumnItemText}>
                          {t(row.i18nKey)}
                        </span>
                      </li>
                    ) : null,
                  )}
                </ul>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
