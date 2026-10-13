import { resolvePlanCheckoutPresentation } from '@/lib/billingCheckoutContracts';
import type { PaymentOption } from '@/types/payment';
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
} from '@/lib/billing';
import type {
  BillingCheckoutOperation,
  BillingPlan,
  BillingProvider,
  BillingSubscription,
  BillingSubscriptionCheckoutAction,
  BillingTrialOffer,
} from '@/types/billing';
import { cn } from '@/lib/utils';
import { formatBillingLearningTime } from '@/lib/billingLearningTime';
import { getFreeFeatureData, getPlanFeatureData } from './BillingOverviewCards';
import styles from './BillingPlanComparisonTable.module.scss';

// Language-neutral typographic markers that anchor each metric row label
// to the matching footnote item. Not user-facing copy, so they stay out of
// i18n.
const ROW_MARKER_LEARNING_TIME = '*';
const ROW_MARKER_VALIDITY = '**';
const MIN_PLAN_COLUMN_WIDTH_PX = 180;

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

function shortenIntervalLabel(label: string): string {
  if (!label) return '';
  return label
    .replace(/^每\s*/, '')
    .replace(/^per\s*/i, '')
    .trim();
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
  badgeLabel?: string;
  campaignLabel?: string;
  originalPriceLabel?: string;
  priceLabel: string;
  periodLabel: string;
  creditAmount: string;
  featured: boolean;
  validityShort: string;
  learningTimeLabel: string;
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
  paymentOptions?: PaymentOption[];
  checkoutOperations?: Record<string, BillingCheckoutOperation>;
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
  paymentOptions,
  checkoutOperations,
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
  const hasPendingPreorder = Boolean(
    hasActiveSubscription && currentSubscription?.next_product_bid,
  );

  const columns: ColumnDescriptor[] = [];

  if (renderFreeColumn) {
    const trialFeatureSet = new Set(trialFeatureKeys);
    columns.push({
      key: 'free',
      testId: 'billing-plan-card-free',
      title: resolveBillingProductTitle(
        t,
        trialOffer,
        t('module.billing.package.free.title'),
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
      learningTimeLabel: formatBillingLearningTime(
        t,
        trialOffer?.credit_amount || 0,
        i18n.language,
      ),
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
    const {
      action,
      actionProvider,
      actionLabelKey,
      actionDisabled,
      actionTone,
      actionTooltipKey,
    } = resolvePlanCheckoutPresentation({
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
      operation: checkoutOperations?.[plan.product_bid],
    });

    const checkoutKey = actionProvider
      ? `plan:${actionProvider}:${plan.product_bid}:${action || 'subscription'}`
      : null;
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
      learningTimeLabel: formatBillingLearningTime(
        t,
        plan.credit_amount,
        i18n.language,
      ),
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
      <table
        className={styles.table}
        style={{ minWidth: columns.length * MIN_PLAN_COLUMN_WIDTH_PX }}
      >
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
          <tr className={styles.dataRow}>
            {columns.map(col => (
              <td
                key={col.key}
                className={cn(col.featured && styles.featuredColumn)}
              >
                <div className={styles.cellLabel}>
                  {t('module.billing.package.learningTime.label')}
                  <sup className='ml-1 font-medium'>
                    {ROW_MARKER_LEARNING_TIME}
                  </sup>
                </div>
                <div
                  className={styles.cellValue}
                  data-testid={`${col.testId}-learning-hours`}
                >
                  {col.learningTimeLabel}
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
                  <sup className='ml-1 font-medium'>{ROW_MARKER_VALIDITY}</sup>
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
