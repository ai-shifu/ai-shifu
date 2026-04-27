import { Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import type { BillingPlan } from '@/types/billing';
import { cn } from '@/lib/utils';
import styles from './BillingOverviewCards.module.scss';

export type ShowcaseTab = 'plans' | 'topup';

type PlanFeatureData = {
  includesLabel?: string;
  items: string[];
};

const COMMON_FEATURE_KEYS: string[] = [
  'module.billing.package.features.common.allTeachingAndLearning',
];

const DEFAULT_FREE_FEATURE_KEYS: string[] = COMMON_FEATURE_KEYS;

const PLAN_FEATURE_INCLUDE_LABELS: Record<string, string> = {
  'creator-plan-yearly': 'module.billing.package.features.pro.includesLabel',
  'creator-plan-yearly-premium':
    'module.billing.package.features.premium.includesLabel',
};

const PLAN_FEATURE_FALLBACK_KEYS: Record<string, string[]> = {
  'creator-plan-monthly': COMMON_FEATURE_KEYS,
  'creator-plan-monthly-pro': COMMON_FEATURE_KEYS,
  'creator-plan-yearly-lite': [
    ...COMMON_FEATURE_KEYS,
    'module.billing.package.features.common.higherConcurrency',
  ],
  'creator-plan-yearly': [
    'module.billing.package.features.yearly.pro.branding',
    'module.billing.package.features.yearly.pro.domain',
  ],
  'creator-plan-yearly-premium': [
    'module.billing.package.features.yearly.premium.priority',
    'module.billing.package.features.yearly.premium.support',
  ],
};

const PLAN_SCALE_KEYS: Record<string, { students: string }> = {
  'creator-plan-trial': {
    students: 'module.billing.package.scale.free.students',
  },
  'creator-plan-monthly': {
    students: 'module.billing.package.scale.lite.students',
  },
  'creator-plan-monthly-pro': {
    students: 'module.billing.package.scale.basic.students',
  },
  'creator-plan-yearly-lite': {
    students: 'module.billing.package.scale.advanced.students',
  },
  'creator-plan-yearly': {
    students: 'module.billing.package.scale.pro.students',
  },
  'creator-plan-yearly-premium': {
    students: 'module.billing.package.scale.premium.students',
  },
};

export function getPlanFeatureData(product: BillingPlan): PlanFeatureData {
  if (PLAN_FEATURE_FALLBACK_KEYS[product.product_code]) {
    return {
      includesLabel: PLAN_FEATURE_INCLUDE_LABELS[product.product_code],
      items: PLAN_FEATURE_FALLBACK_KEYS[product.product_code],
    };
  }

  const productHighlights = product.highlights?.filter(item => Boolean(item));
  if (productHighlights && productHighlights.length > 0) {
    return {
      includesLabel: PLAN_FEATURE_INCLUDE_LABELS[product.product_code],
      items: productHighlights,
    };
  }

  if (product.billing_interval === 'day') {
    return {
      items: [
        'module.billing.package.features.daily.publish',
        'module.billing.package.features.daily.preview',
        'module.billing.package.features.daily.support',
      ],
    };
  }

  if (product.billing_interval === 'year') {
    return {
      items: PLAN_FEATURE_FALLBACK_KEYS['creator-plan-yearly'],
    };
  }

  return {
    items: PLAN_FEATURE_FALLBACK_KEYS['creator-plan-monthly'],
  };
}

export function getFreeFeatureData(_highlights?: string[]): PlanFeatureData {
  return {
    items: DEFAULT_FREE_FEATURE_KEYS,
  };
}

export function getPlanScaleKeys(
  productCode: string,
): { students: string } | null {
  return PLAN_SCALE_KEYS[productCode] || null;
}

type TopupCardProps = {
  actionLabel: string;
  actionLoading?: boolean;
  creditsLabel: string;
  description?: string;
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
          {description ? (
            <div className={styles.topupCardDescription}>{description}</div>
          ) : null}
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
