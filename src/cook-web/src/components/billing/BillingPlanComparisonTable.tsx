import { InformationCircleIcon } from '@heroicons/react/24/outline';
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
  formatBillingPlanInterval,
  resolveBillingProductTitle,
  resolveBillingProductDescription,
} from '@/lib/billing';
import type {
  BillingPlan,
  BillingProvider,
  BillingTrialOffer,
} from '@/types/billing';
import { cn } from '@/lib/utils';
import {
  getFreeFeatureData,
  getPlanFeatureData,
  getPlanScaleKeys,
} from './BillingOverviewCards';
import styles from './BillingPlanComparisonTable.module.scss';

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
): BillingProvider | null {
  if (stripeAvailable) return 'stripe';
  if (pingxxAvailable) return 'pingxx';
  return null;
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
  priceLabel: string;
  periodLabel: string;
  creditAmount: string;
  featured: boolean;
  validityShort: string;
  validityTooltip: string;
  studentLabel?: string;
  features: boolean[];
  action: ColumnAction;
};

type BillingTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

function resolvePlanValidityDisplay(
  t: BillingTranslator,
  plan: BillingPlan,
): { short: string; tooltip: string } {
  const intervalCount = Math.max(plan.billing_interval_count || 0, 1);
  const isMultiCycle = intervalCount > 1;
  if (plan.billing_interval === 'month') {
    return {
      short: isMultiCycle
        ? t('module.billing.package.validityShort.monthlyMonths', {
            count: intervalCount,
          })
        : t('module.billing.package.validityShort.monthly'),
      tooltip: isMultiCycle
        ? ''
        : t('module.billing.package.validityTooltip.monthly'),
    };
  }
  if (plan.billing_interval === 'year') {
    return {
      short: isMultiCycle
        ? t('module.billing.package.validityShort.yearlyYears', {
            count: intervalCount,
          })
        : t('module.billing.package.validityShort.yearly'),
      tooltip: isMultiCycle
        ? ''
        : t('module.billing.package.validityTooltip.yearly'),
    };
  }
  return { short: '', tooltip: '' };
}

export type BillingPlanComparisonTableProps = {
  trialOffer: BillingTrialOffer | null | undefined;
  paidPlans: BillingPlan[];
  orderedPlans: BillingPlan[];
  currentPlan: BillingPlan | null;
  hasActiveSubscription: boolean;
  isTrialCurrentPlan: boolean;
  renderFreeColumn: boolean;
  checkoutLoadingKey: string;
  stripeAvailable: boolean;
  pingxxAvailable: boolean;
  onSelectPlanCheckout: (plan: BillingPlan, provider: BillingProvider) => void;
};

export function BillingPlanComparisonTable({
  trialOffer,
  paidPlans,
  orderedPlans,
  currentPlan,
  hasActiveSubscription,
  isTrialCurrentPlan,
  renderFreeColumn,
  checkoutLoadingKey,
  stripeAvailable,
  pingxxAvailable,
  onSelectPlanCheckout,
}: BillingPlanComparisonTableProps) {
  const { t, i18n } = useTranslation();
  const processingLabel = t('module.billing.catalog.actions.processing');
  const emptyValue = t('module.billing.package.table.emptyValue');
  const trialFeatureKeys = getFreeFeatureData().items;
  const featureRows = buildFeatureRows(trialFeatureKeys, paidPlans);
  const provider = resolveCheckoutProvider(stripeAvailable, pingxxAvailable);
  const currentRank = planRankIn(
    orderedPlans,
    currentPlan?.product_bid || null,
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
          : t('module.billing.package.free.priceValue'),
      periodLabel: '',
      creditAmount: t('module.billing.package.topup.creditLabel', {
        credits: formatBillingCreditAmount(trialOffer?.credit_amount || 0),
      }),
      featured: isTrialCurrentPlan || !hasActiveSubscription,
      validityShort: t('module.billing.package.validityShort.free', {
        days: trialOffer?.valid_days || 15,
      }),
      validityTooltip: t('module.billing.package.validityTooltip.free', {
        days: trialOffer?.valid_days || 15,
      }),
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
    const planRank = planRankIn(orderedPlans, plan.product_bid);
    const isDowngradeLocked =
      hasActiveSubscription &&
      !isCurrentPlan &&
      currentRank >= 0 &&
      planRank >= 0 &&
      planRank < currentRank;
    const checkoutKey = provider
      ? `plan:${provider}:${plan.product_bid}`
      : null;
    const planScale = getPlanScaleKeys(plan.product_code);
    const badgeKey = plan.status_badge_key;

    columns.push({
      key: plan.product_bid,
      testId: `billing-plan-card-${plan.product_bid}`,
      title: resolveBillingProductTitle(t, plan),
      description: resolveBillingProductDescription(t, plan),
      badgeLabel: badgeKey ? t(badgeKey) : undefined,
      priceLabel: formatBillingPrice(
        plan.price_amount,
        plan.currency,
        i18n.language,
      ),
      periodLabel: shortenIntervalLabel(formatBillingPlanInterval(t, plan)),
      creditAmount: t('module.billing.package.topup.creditLabel', {
        credits: formatBillingCreditAmount(plan.credit_amount),
      }),
      featured: isCurrentPlan,
      ...(() => {
        const v = resolvePlanValidityDisplay(t, plan);
        return { validityShort: v.short, validityTooltip: v.tooltip };
      })(),
      studentLabel: planScale ? t(planScale.students) : undefined,
      features: featureRows.map(
        row => row.unlockIndex === -1 || idx >= row.unlockIndex,
      ),
      action: {
        label: isCurrentPlan
          ? t('module.billing.package.actions.currentSubscription')
          : isDowngradeLocked
            ? t('module.billing.package.actions.downgradeDisabled')
            : hasActiveSubscription
              ? t('module.billing.package.actions.upgradeNow')
              : t('module.billing.package.actions.subscribeNow'),
        loading: checkoutKey !== null && checkoutLoadingKey === checkoutKey,
        disabled: !provider || isCurrentPlan || isDowngradeLocked,
        tone: isCurrentPlan
          ? 'current'
          : isDowngradeLocked
            ? 'muted'
            : 'primary',
        tooltip: isDowngradeLocked
          ? t('module.billing.package.actions.upgradeOnlyTooltip')
          : undefined,
        onClick: () => provider && onSelectPlanCheckout(plan, provider),
        testId: `billing-plan-card-${plan.product_bid}-action`,
      },
    });
  });

  if (columns.length === 0) {
    return null;
  }

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
                key={col.key}
                className={cn(
                  styles.columnHead,
                  col.featured && styles.featuredColumn,
                )}
                data-testid={col.testId}
                data-featured={col.featured ? 'true' : 'false'}
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
                <div className={styles.columnPrice}>
                  {col.periodLabel
                    ? `${col.priceLabel} / ${col.periodLabel}`
                    : col.priceLabel}
                </div>
                <div className={styles.columnCreditAmount}>
                  {col.creditAmount}
                </div>
                {col.action.tooltip ? (
                  <TooltipProvider delayDuration={0}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className={styles.columnActionWrap}
                          data-testid={`${col.action.testId}-trigger`}
                          tabIndex={0}
                        >
                          <Button
                            className={cn(
                              styles.columnAction,
                              col.action.tone === 'current' &&
                                'disabled:opacity-100',
                            )}
                            data-testid={col.action.testId}
                            disabled={col.action.disabled || col.action.loading}
                            onClick={col.action.onClick}
                            type='button'
                            variant={TONE_VARIANT[col.action.tone]}
                          >
                            {col.action.loading
                              ? processingLabel
                              : col.action.label}
                          </Button>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>{col.action.tooltip}</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : (
                  <Button
                    className={cn(
                      styles.columnAction,
                      col.action.tone === 'current' &&
                        'disabled:opacity-100',
                    )}
                    data-testid={col.action.testId}
                    disabled={col.action.disabled || col.action.loading}
                    onClick={col.action.onClick}
                    type='button'
                    variant={TONE_VARIANT[col.action.tone]}
                  >
                    {col.action.loading ? processingLabel : col.action.label}
                  </Button>
                )}
              </th>
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
                </div>
                <div className={styles.cellValue}>
                  <TooltipProvider delayDuration={0}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className={styles.validityHint}
                          tabIndex={col.validityTooltip ? 0 : -1}
                        >
                          {col.validityShort || emptyValue}
                          {col.validityTooltip ? (
                            <InformationCircleIcon
                              className={styles.validityIcon}
                            />
                          ) : null}
                        </span>
                      </TooltipTrigger>
                      {col.validityTooltip ? (
                        <TooltipContent className={styles.validityTooltipBody}>
                          {col.validityTooltip}
                        </TooltipContent>
                      ) : null}
                    </Tooltip>
                  </TooltipProvider>
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
