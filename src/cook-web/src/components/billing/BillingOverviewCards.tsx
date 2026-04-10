import type { ReactNode } from 'react';
import { CheckIcon, InformationCircleIcon } from '@heroicons/react/24/outline';
import { Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import type { BillingPlan } from '@/types/billing';
import { cn } from '@/lib/utils';
import styles from './BillingOverviewCards.module.scss';

export type ShowcaseTab = 'monthly' | 'yearly' | 'topup';

export function getPlanFeatureKeys(product: BillingPlan): string[] {
  const productHighlights = product.highlights?.filter(item => Boolean(item));
  if (productHighlights && productHighlights.length > 0) {
    return productHighlights;
  }
  if (product.billing_interval === 'year') {
    return [
      'module.billing.package.features.yearly.pro.branding',
      'module.billing.package.features.yearly.pro.domain',
      'module.billing.package.features.yearly.pro.priority',
      'module.billing.package.features.yearly.pro.analytics',
      'module.billing.package.features.yearly.pro.support',
    ];
  }
  return [
    'module.billing.package.features.monthly.publish',
    'module.billing.package.features.monthly.preview',
    'module.billing.package.features.monthly.support',
  ];
}

export function getFreeFeatureKeys(): string[] {
  return [
    'module.billing.package.features.free.publish',
    'module.billing.package.features.free.preview',
  ];
}

export function PlanFeatureList({ items }: { items: string[] }) {
  const { t } = useTranslation();

  return (
    <div>
      <p className={styles.planFeatureListTitle}>
        {t('module.billing.package.featuresTitle')}
      </p>
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
  compact?: boolean;
  creditSummary: string;
  creditValidityLabel: string;
  description: string;
  disabled?: boolean;
  featured?: boolean;
  footer: ReactNode;
  onAction?: () => void;
  priceLabel: string;
  priceMetaLabel?: string;
  testId: string;
  title: string;
};

export function PlanShowcaseCard({
  actionLabel,
  actionLoading = false,
  compact = false,
  creditSummary,
  creditValidityLabel,
  description,
  disabled = false,
  featured = false,
  footer,
  onAction,
  priceLabel,
  priceMetaLabel,
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
        <h3 className={styles.planShowcaseCardTitle}>{title}</h3>
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

      <div className={styles.planShowcaseCardCreditBox}>
        <div className={styles.planShowcaseCardCreditTitle}>
          {creditSummary}
        </div>
        <div className={styles.planShowcaseCardCreditValidity}>
          {creditValidityLabel}
        </div>
      </div>

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
