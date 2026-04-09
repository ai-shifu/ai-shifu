import React, { useMemo } from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
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
import { useBillingOverview } from '@/hooks/useBillingOverview';
import { useBillingWalletBuckets } from '@/hooks/useBillingWalletBuckets';
import type {
  BillingBucketCategory,
  BillingWalletBucket,
} from '@/types/billing';
import {
  formatBillingCredits,
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

const CATEGORY_ORDER: BillingBucketCategory[] = [
  'free',
  'subscription',
  'topup',
];

function formatDetailWindow(value: string | null): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
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
      <div className='space-y-3'>
        <div className='inline-flex rounded-xl border border-slate-200 bg-white px-3 py-1 text-sm font-medium text-slate-500 shadow-sm'>
          {t('module.billing.page.tabs.ledger')}
        </div>
        <div className='space-y-2'>
          <h1 className='text-3xl font-semibold tracking-tight text-slate-950 md:text-4xl'>
            {t('module.billing.details.title')}
          </h1>
          <p className='max-w-3xl text-sm leading-7 text-slate-500 md:text-base'>
            {t('module.billing.details.subtitle')}
          </p>
        </div>
      </div>

      <Card className='overflow-hidden rounded-[32px] border-slate-200 bg-[linear-gradient(180deg,#f8fbff_0%,#ffffff_100%)] shadow-[0_22px_60px_rgba(15,23,42,0.08)]'>
        <CardHeader className='gap-6 border-b border-slate-100 pb-8 md:flex-row md:items-start md:justify-between'>
          <div className='space-y-4'>
            <div className='flex flex-wrap items-end gap-4'>
              <CardTitle className='text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl'>
                {t('module.billing.details.totalCreditsLabel')}
              </CardTitle>
              {overviewLoading ? (
                <Skeleton className='h-12 w-36 rounded-xl' />
              ) : (
                <div className='text-3xl font-semibold tracking-tight text-slate-950 md:text-4xl'>
                  {totalCreditsLabel}
                </div>
              )}
            </div>
            <CardDescription className='max-w-3xl text-sm leading-7 text-slate-500 md:text-base'>
              {t('module.billing.details.totalCreditsDescription')}
            </CardDescription>
          </div>

          <Button
            className='h-11 rounded-2xl bg-slate-950 px-5 text-sm font-semibold text-white hover:bg-slate-800 md:text-base'
            onClick={onUpgrade}
            type='button'
          >
            {t('module.billing.details.actions.upgradeNow')}
          </Button>
        </CardHeader>

        <CardContent className='pt-8'>
          {loadError ? (
            <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
              {t('module.billing.ledger.loadError')}
            </div>
          ) : null}

          <div className='overflow-hidden rounded-[28px] border border-slate-200 bg-white'>
            <div className='grid grid-cols-[1.4fr_0.7fr_0.9fr] gap-4 border-b border-slate-200 px-6 py-5 text-sm font-medium text-slate-500'>
              <div className='flex items-center gap-2'>
                <span>{t('module.billing.details.table.creditType')}</span>
                <QuestionMarkCircleIcon className='h-5 w-5 text-slate-300' />
              </div>
              <div className='text-right'>
                {t('module.billing.details.table.balance')}
              </div>
              <div className='text-right'>
                {t('module.billing.details.table.validUntil')}
              </div>
            </div>

            {bucketsLoading ? (
              <div className='space-y-4 px-6 py-6'>
                <Skeleton className='h-12 rounded-2xl' />
                <Skeleton className='h-12 rounded-2xl' />
                <Skeleton className='h-12 rounded-2xl' />
              </div>
            ) : (
              <div>
                {summaryRows.map(row => (
                  <div
                    key={row.category}
                    className='grid grid-cols-[1.4fr_0.7fr_0.9fr] gap-4 border-b border-slate-100 px-6 py-5 text-sm text-slate-700 last:border-b-0 md:text-base'
                  >
                    <div className='font-semibold text-slate-950'>
                      {resolveBillingBucketCategoryLabel(t, row.category)}
                    </div>
                    <div className='text-right font-medium text-slate-950'>
                      {formatBillingCredits(
                        row.availableCredits,
                        i18n.language,
                      )}
                    </div>
                    <div className='text-right text-slate-600'>
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
