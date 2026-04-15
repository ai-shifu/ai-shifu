import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import {
  useBillingOverview,
  useBillingWalletBuckets,
} from '@/hooks/useBillingData';
import type {
  BillingBucketCategory,
  BillingWalletBucket,
} from '@/types/billing';
import {
  formatBillingCredits,
  parseBillingDateValue,
  registerBillingTranslationUsage,
  resolveBillingBucketCategoryLabel,
} from '@/lib/billing';

type BillingCreditDetailsPanelProps = {
  onUpgrade?: () => void;
};

type CategorySummaryRow = {
  category: BillingBucketCategory;
  availableCredits: number;
  effectiveTo: string | null;
};

const CATEGORY_ORDER: BillingBucketCategory[] = ['subscription', 'topup'];

function formatDetailWindow(value: string | null): string {
  const date = parseBillingDateValue(value);
  if (!date) {
    return '';
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${year}.${month}.${day} ${hour}:${minute}`;
}

function buildCategorySummary(
  buckets: BillingWalletBucket[],
): CategorySummaryRow[] {
  return CATEGORY_ORDER.map(category => {
    const activeBuckets = buckets
      .filter(
        bucket => bucket.category === category && bucket.status === 'active',
      )
      .sort((left, right) =>
        String(left.effective_to || '').localeCompare(
          String(right.effective_to || ''),
        ),
      );

    return {
      category,
      availableCredits: activeBuckets.reduce(
        (sum, bucket) => sum + Number(bucket.available_credits || 0),
        0,
      ),
      effectiveTo:
        activeBuckets.find(bucket => bucket.effective_to)?.effective_to || null,
    };
  });
}

export function BillingCreditDetailsPanel({
  onUpgrade,
}: BillingCreditDetailsPanelProps) {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const {
    data: overview,
    error: overviewError,
    isLoading: overviewLoading,
  } = useBillingOverview();
  const {
    data: bucketList,
    error: bucketsError,
    isLoading: bucketsLoading,
  } = useBillingWalletBuckets();

  const summaryRows = useMemo(
    () => buildCategorySummary(bucketList?.items || []),
    [bucketList?.items],
  );

  const totalCreditsLabel = formatBillingCredits(
    overview?.wallet.available_credits || 0,
    i18n.language,
  );
  const neverExpiresLabel = t('module.billing.ledger.neverExpires');
  const loadError = overviewError || bucketsError;

  return (
    <section
      className='space-y-6'
      data-testid='billing-credit-details-panel'
    >
      <div>
        <h1 className='text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl'>
          {t('module.billing.details.title')}
        </h1>
      </div>

      <Card className='gap-[var(--spacing-6,24px)] overflow-hidden rounded-[var(--border-radius-rounded-lg,10px)] border border-[var(--base-border,#E5E5E5)] bg-[#F6FAFF] shadow-[var(--shadow-xs-offset-x,0)_var(--shadow-xs-offset-y,1px)_var(--shadow-xs-blur-radius,2px)_var(--shadow-xs-spread-radius,0)_var(--shadow-xs-color,rgba(0,0,0,0.05))]'>
        <CardHeader className='gap-6 px-6 pb-0 pt-6 md:flex-row md:items-start md:justify-between'>
          <div className='space-y-1.5'>
            <div className='flex flex-wrap items-end gap-4'>
              <CardTitle className='text-[length:var(--text-2xl-font-size,24px)] font-[var(--font-weight-semibold,600)] leading-[var(--text-2xl-line-height,32px)] tracking-[var(--typography-components-h3-letter-spacing,-0.4px)] text-[var(--base-card-foreground,#0A0A0A)]'>
                {t('module.billing.details.totalCreditsLabel')}
              </CardTitle>
              {overviewLoading ? (
                <Skeleton className='h-12 w-36 rounded-xl' />
              ) : (
                <div className='text-[length:var(--text-2xl-font-size,24px)] font-[var(--font-weight-semibold,600)] leading-[var(--text-2xl-line-height,32px)] tracking-[var(--typography-components-h3-letter-spacing,-0.4px)] text-[var(--base-card-foreground,#0A0A0A)]'>
                  {totalCreditsLabel}
                </div>
              )}
            </div>
            <CardDescription className='max-w-3xl text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
              {t('module.billing.details.totalCreditsDescription')}
            </CardDescription>
          </div>

          <Button
            className='h-[var(--height-h-9,36px)] gap-[var(--spacing-2,8px)] rounded-[var(--border-radius-rounded-md,8px)] bg-[var(--base-primary,#171717)] px-[var(--spacing-4,16px)] py-[var(--spacing-2,8px)] text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-primary-foreground,#FAFAFA)] shadow-[var(--shadow-xs-offset-x,0)_var(--shadow-xs-offset-y,1px)_var(--shadow-xs-blur-radius,2px)_var(--shadow-xs-spread-radius,0)_var(--shadow-xs-color,rgba(0,0,0,0.05))] hover:bg-[var(--base-primary,#171717)]'
            onClick={onUpgrade}
            type='button'
          >
            {t('module.billing.details.actions.upgradeNow')}
          </Button>
        </CardHeader>

        <CardContent className='px-6 pb-0 pt-5'>
          {loadError ? (
            <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
              {t('module.billing.ledger.loadError')}
            </div>
          ) : null}

          <div className='mt-0'>
            <div className='grid grid-cols-[1.4fr_0.7fr_0.9fr] border-b border-[var(--base-border,#E5E5E5)]'>
              <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center gap-2 px-[var(--spacing-2,8px)] text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
                <span>{t('module.billing.details.table.creditType')}</span>
              </div>
              <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center justify-end px-[var(--spacing-2,8px)] text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
                {t('module.billing.details.table.balance')}
              </div>
              <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center justify-end px-[var(--spacing-2,8px)] text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
                {t('module.billing.details.table.validUntil')}
              </div>
            </div>

            {bucketsLoading ? (
              <div className='space-y-4 px-2 py-4'>
                <Skeleton className='h-12 rounded-2xl' />
                <Skeleton className='h-12 rounded-2xl' />
                <Skeleton className='h-12 rounded-2xl' />
              </div>
            ) : (
              <div>
                {summaryRows.map(row => (
                  <div
                    key={row.category}
                    className='grid grid-cols-[1.4fr_0.7fr_0.9fr] border-b border-[var(--base-border,#E5E5E5)] last:border-b-0'
                  >
                    <div className='px-[var(--spacing-2,8px)] py-4 text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                      {resolveBillingBucketCategoryLabel(t, row.category)}
                    </div>
                    <div className='px-[var(--spacing-2,8px)] py-4 text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                      {formatBillingCredits(
                        row.availableCredits,
                        i18n.language,
                      )}
                    </div>
                    <div className='px-[var(--spacing-2,8px)] py-4 text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                      {row.effectiveTo
                        ? formatDetailWindow(row.effectiveTo)
                        : neverExpiresLabel}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
