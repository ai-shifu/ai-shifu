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
  resolveBillingPlanCreditsLabel,
  resolveBillingPlanValidityLabel,
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

function planRankIn(
  ordered: BillingPlan[],
  productBid: string | null,
): number {
  if (!productBid) return -1;
  return ordered.findIndex(plan => plan.product_bid === productBid);
}

function resolveCheckoutProvider(
  stripeAvailable: boolean,
  pingxxAvailable: boolean,
): BillingProvider | null {
  if (stripeAvailable) return 'stripe';
  if (pingxxAvailable) return 'pingxx';
  return null;
}

type ColumnAction = {
  label: string;
  loading: boolean;
  disabled: boolean;
  tooltip?: string;
  onClick?: () => void;
  testId: string;
};

type ColumnDescriptor = {
  key: string;
  testId: string;
  title: string;
  description: string;
  badgeLabel?: string;
  priceLabel: string;
  priceMetaLabel?: string;
  featured: boolean;
  creditLabel: string;
  validityLabel: string;
  studentLabel?: string;
  features: boolean[];
  action: ColumnAction;
};

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
      featured: isTrialCurrentPlan || !hasActiveSubscription,
      creditLabel: t('module.billing.package.free.creditSummary', {
        credits: formatBillingCreditAmount(trialOffer?.credit_amount || 0),
      }),
      validityLabel: t('module.billing.package.validity.free'),
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
      : '';
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
      priceMetaLabel: formatBillingPlanInterval(t, plan),
      featured: isCurrentPlan,
      creditLabel: resolveBillingPlanCreditsLabel(t, plan),
      validityLabel: resolveBillingPlanValidityLabel(t, plan),
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
        loading: checkoutLoadingKey === checkoutKey,
        disabled: !provider || isCurrentPlan || isDowngradeLocked,
        tooltip: isDowngradeLocked
          ? t('module.billing.package.actions.upgradeOnlyTooltip')
          : undefined,
        onClick: () => provider && onSelectPlanCheckout(plan, provider),
        testId: `billing-plan-card-${plan.product_bid}-action`,
      },
    });
  });

  return (
    <div
      className={styles.tableWrapper}
      data-testid='billing-plan-comparison-table'
    >
      <table className={styles.table}>
        <colgroup>
          {columns.map(col => (
            <col key={col.key} />
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
                <div className={styles.columnDescription}>{col.description}</div>
                <div className={styles.columnPriceRow}>
                  <span className={styles.columnPrice}>{col.priceLabel}</span>
                  {col.priceMetaLabel ? (
                    <span className={styles.columnPriceMeta}>
                      {col.priceMetaLabel}
                    </span>
                  ) : null}
                </div>
                {col.action.tooltip ? (
                  <TooltipProvider delayDuration={0}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className={styles.columnActionWrap}
                          data-testid={`${col.action.testId}-trigger`}
                        >
                          <Button
                            className={styles.columnAction}
                            data-testid={col.action.testId}
                            disabled={col.action.disabled || col.action.loading}
                            onClick={col.action.onClick}
                            type='button'
                            variant='secondary'
                          >
                            {col.action.loading ? '...' : col.action.label}
                          </Button>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>{col.action.tooltip}</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : (
                  <Button
                    className={styles.columnAction}
                    data-testid={col.action.testId}
                    disabled={col.action.disabled || col.action.loading}
                    onClick={col.action.onClick}
                    type='button'
                    variant='secondary'
                  >
                    {col.action.loading ? '...' : col.action.label}
                  </Button>
                )}
              </th>
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
                  {t('module.billing.package.table.creditsRowLabel')}
                </div>
                <div className={styles.cellValue}>{col.creditLabel}</div>
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
                  {col.studentLabel || '—'}
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
                <div className={styles.cellValue}>{col.validityLabel}</div>
              </td>
            ))}
          </tr>
          <tr className={styles.featureSectionRow}>
            <th
              colSpan={columns.length}
              scope='colgroup'
            >
              {t('module.billing.package.table.featuresRowLabel')}
            </th>
          </tr>
          <tr className={styles.featureColumnRow}>
            {columns.map(col => (
              <td
                key={col.key}
                className={cn(col.featured && styles.featuredColumn)}
              >
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
