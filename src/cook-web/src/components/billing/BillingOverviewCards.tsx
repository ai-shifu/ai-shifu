import type { ReactNode } from 'react';
import { CheckIcon, InformationCircleIcon, UserGroupIcon } from '@heroicons/react/24/outline';
import { Sparkles, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { BillingPlan } from '@/types/billing';
import { cn } from '@/lib/utils';
import styles from './BillingOverviewCards.module.scss';

export type ShowcaseTab = 'monthly' | 'yearly' | 'topup';

type PlanFeatureData = {
  includesLabel?: string;
  items: string[];
};

const BASE_FEATURE_KEYS: string[] = [
  'module.billing.package.features.base.courseCreate',
  'module.billing.package.features.base.studentImport',
  'module.billing.package.features.base.aiListen',
  'module.billing.package.features.base.dataQuery',
];

const PLAN_FEATURE_DATA: Record<string, PlanFeatureData> = {
  'creator-plan-monthly': { items: BASE_FEATURE_KEYS },
  'creator-plan-monthly-pro': { items: BASE_FEATURE_KEYS },
  'creator-plan-yearly-lite': {
    includesLabel: 'module.billing.package.features.advanced.includesLabel',
    items: [
      'module.billing.package.features.advanced.taskPriority',
      'module.billing.package.features.advanced.parallelProcessing',
      'module.billing.package.features.advanced.techBasic',
    ],
  },
  'creator-plan-yearly': {
    includesLabel: 'module.billing.package.features.pro.includesLabel',
    items: [
      'module.billing.package.features.pro.branding',
      'module.billing.package.features.pro.customDomain',
      'module.billing.package.features.pro.techPriority',
    ],
  },
  'creator-plan-yearly-premium': {
    includesLabel: 'module.billing.package.features.premium.includesLabel',
    items: [
      'module.billing.package.features.premium.concurrencyQuota',
      'module.billing.package.features.premium.dedicatedSupport',
      'module.billing.package.features.premium.onboarding',
    ],
  },
};

const PLAN_SCALE_KEYS: Record<string, { students: string; courses: string }> = {
  'creator-plan-trial': {
    students: 'module.billing.package.scale.free.students',
    courses: 'module.billing.package.scale.free.courses',
  },
  'creator-plan-monthly': {
    students: 'module.billing.package.scale.lite.students',
    courses: 'module.billing.package.scale.lite.courses',
  },
  'creator-plan-monthly-pro': {
    students: 'module.billing.package.scale.basic.students',
    courses: 'module.billing.package.scale.basic.courses',
  },
  'creator-plan-yearly-lite': {
    students: 'module.billing.package.scale.advanced.students',
    courses: 'module.billing.package.scale.advanced.courses',
  },
  'creator-plan-yearly': {
    students: 'module.billing.package.scale.pro.students',
    courses: 'module.billing.package.scale.pro.courses',
  },
  'creator-plan-yearly-premium': {
    students: 'module.billing.package.scale.premium.students',
    courses: 'module.billing.package.scale.premium.courses',
  },
};

export function getPlanFeatureData(product: BillingPlan): PlanFeatureData {
  return PLAN_FEATURE_DATA[product.product_code] || { items: BASE_FEATURE_KEYS };
}

export function getFreeFeatureData(): PlanFeatureData {
  return { items: BASE_FEATURE_KEYS };
}

export function getPlanScaleKeys(
  productCode: string,
): { students: string; courses: string } | null {
  return PLAN_SCALE_KEYS[productCode] || null;
}

export function PlanFeatureList({
  includesLabel,
  items,
}: {
  includesLabel?: string;
  items: string[];
}) {
  const { t } = useTranslation();

  return (
    <div>
      {includesLabel ? (
        <div className={styles.planFeatureIncludesLabel}>
          {t(includesLabel)}
        </div>
      ) : (
        <p className={styles.planFeatureListTitle}>
          {t('module.billing.package.featuresTitle')}
        </p>
      )}
      <ul className={styles.planFeatureList}>
        {items.map(item => (
          <li
            key={item}
            className={styles.planFeatureListItem}
          >
            <div className={styles.planFeatureListItemContent}>
              <CheckIcon className={styles.planFeatureListCheckIcon} />
              <span className={styles.planFeatureListItemText}>{t(item)}</span>
            </div>
            <InformationCircleIcon className={styles.planFeatureListInfoIcon} />
          </li>
        ))}
      </ul>
    </div>
  );
}

type PlanShowcaseCardProps = {
  actionLabel: string;
  actionLoading?: boolean;
  actionTooltip?: string;
  badgeLabel?: string;
  compact?: boolean;
  courseScope?: string;
  creditSummary: string;
  creditValidityLabel: string;
  description: string;
  disabled?: boolean;
  featured?: boolean;
  footer: ReactNode;
  onAction?: () => void;
  priceLabel: string;
  priceMetaLabel?: string;
  studentCapacity?: string;
  testId: string;
  title: string;
};

export function PlanShowcaseCard({
  actionLabel,
  actionLoading = false,
  actionTooltip,
  badgeLabel,
  compact = false,
  courseScope,
  creditSummary,
  creditValidityLabel,
  description,
  disabled = false,
  featured = false,
  footer,
  onAction,
  priceLabel,
  priceMetaLabel,
  studentCapacity,
  testId,
  title,
}: PlanShowcaseCardProps) {
  return (
    <div
      className={cn(
        'flex h-full flex-col p-8 transition-all',
        compact ? 'min-h-[260px]' : '',
        styles.planShowcaseCard,
        featured && styles.planShowcaseCardActive,
      )}
      data-featured={featured ? 'true' : 'false'}
      data-testid={testId}
    >
      <div className={styles.planShowcaseCardHeader}>
        <div className={styles.planShowcaseCardTitleRow}>
          <h3 className={styles.planShowcaseCardTitle}>{title}</h3>
          {badgeLabel ? (
            <span className={styles.planShowcaseCardBadge}>
              <Star className={styles.planShowcaseCardBadgeIcon} />
              {badgeLabel}
            </span>
          ) : null}
        </div>
        <p className={styles.planShowcaseCardDescription}>{description}</p>
      </div>

      <div className={styles.planShowcaseCardPriceRow}>
        <div className={styles.planShowcaseCardPriceValue}>{priceLabel}</div>
        {priceMetaLabel ? (
          <div className={styles.planShowcaseCardPriceMeta}>
            {priceMetaLabel}
          </div>
        ) : null}
      </div>

      {actionTooltip ? (
        <TooltipProvider delayDuration={0}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                className='mt-6 block w-full'
                data-testid={`${testId}-action-trigger`}
              >
                <Button
                  className={cn(
                    'w-full text-sm font-semibold',
                    styles.planShowcaseCardAction,
                  )}
                  data-testid={`${testId}-action`}
                  disabled={disabled || actionLoading}
                  onClick={onAction}
                  type='button'
                  variant='secondary'
                >
                  {actionLoading ? '...' : actionLabel}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{actionTooltip}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : (
        <Button
          className={cn(
            'mt-6 text-sm font-semibold',
            styles.planShowcaseCardAction,
          )}
          data-testid={`${testId}-action`}
          disabled={disabled || actionLoading}
          onClick={onAction}
          type='button'
          variant='secondary'
        >
          {actionLoading ? '...' : actionLabel}
        </Button>
      )}

      <div className={styles.planShowcaseCardCreditBox}>
        <div className={styles.planShowcaseCardCreditTitle}>
          {creditSummary}
        </div>
        <div className={styles.planShowcaseCardCreditValidity}>
          {creditValidityLabel}
        </div>
      </div>

      {studentCapacity || courseScope ? (
        <div className={styles.planShowcaseCardScaleBox}>
          <UserGroupIcon className={styles.planShowcaseCardScaleIcon} />
          <div className={styles.planShowcaseCardScaleText}>
            {studentCapacity}
            {studentCapacity && courseScope ? ' · ' : ''}
            {courseScope}
          </div>
        </div>
      ) : null}

      <div className='mt-8 flex-1'>{footer}</div>
    </div>
  );
}

type TopupCardProps = {
  actionLabel: string;
  actionLoading?: boolean;
  creditsLabel: string;
  description: string;
  disabled?: boolean;
  featured?: boolean;
  onAction?: () => void;
  priceLabel: string;
  testId: string;
};

export function TopupCard({
  actionLabel,
  actionLoading = false,
  creditsLabel,
  description,
  disabled = false,
  featured = false,
  onAction,
  priceLabel,
  testId,
}: TopupCardProps) {
  return (
    <div
      className={cn(styles.topupCard, featured && styles.topupCardFeatured)}
      data-testid={testId}
    >
      <div className={styles.topupCardBody}>
        <div className={styles.topupCardHeader}>
          <div className={styles.topupCardHeading}>
            <Sparkles className={styles.topupCardIcon} />
            <div className={styles.topupCardTitle}>{creditsLabel}</div>
          </div>
          <div className={styles.topupCardDescription}>{description}</div>
        </div>

        <div className={styles.topupCardFooter}>
          <div className={styles.topupCardPrice}>{priceLabel}</div>
          <Button
            className={styles.topupCardAction}
            data-testid={`${testId}-action`}
            disabled={disabled || actionLoading}
            onClick={onAction}
            type='button'
          >
            {actionLoading ? '...' : actionLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
