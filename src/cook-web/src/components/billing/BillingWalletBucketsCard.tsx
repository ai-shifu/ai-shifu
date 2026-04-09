import React, { useMemo } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { Badge } from '@/components/ui/Badge';
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import type {
  BillingWalletBucket,
  BillingWalletBucketList,
} from '@/types/billing';
import {
  formatBillingCredits,
  formatBillingDate,
  registerBillingTranslationUsage,
  resolveBillingBucketCategoryLabel,
  resolveBillingBucketSourceLabel,
  resolveBillingBucketStatusLabel,
  resolveBillingEmptyLabel,
} from '@/lib/billing';
import { BillingMetricCard } from './BillingMetricCard';

const BILLING_WALLET_BUCKETS_SWR_KEY = ['billing-wallet-buckets'];

function resolveBucketStatusClasses(
  status: BillingWalletBucket['status'],
): string {
  if (status === 'active') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (status === 'expired') {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  if (status === 'canceled') {
    return 'border-slate-200 bg-slate-100 text-slate-600';
  }
  return 'border-slate-200 bg-slate-100 text-slate-700';
}

function renderWindowLabel(
  bucket: BillingWalletBucket,
  locale: string,
  emptyLabel: string,
  neverExpiresLabel: string,
): { start: string; end: string } {
  return {
    start: formatBillingDate(bucket.effective_from, locale) || emptyLabel,
    end: bucket.effective_to
      ? formatBillingDate(bucket.effective_to, locale) || neverExpiresLabel
      : neverExpiresLabel,
  };
}

export function BillingWalletBucketsCard() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const {
    data: buckets,
    error,
    isLoading,
  } = useSWR<BillingWalletBucketList>(
    BILLING_WALLET_BUCKETS_SWR_KEY,
    async () =>
      (await api.getBillingWalletBuckets({})) as BillingWalletBucketList,
    {
      revalidateOnFocus: false,
    },
  );
  const bucketList = useMemo(() => buckets?.items || [], [buckets]);

  const summary = useMemo(() => {
    const activeBuckets = bucketList.filter(
      bucket => bucket.status === 'active',
    );
    const nextExpiry = activeBuckets
      .filter(bucket => bucket.effective_to)
      .sort((left, right) =>
        String(left.effective_to).localeCompare(String(right.effective_to)),
      )[0]?.effective_to;

    return {
      activeBucketCount: activeBuckets.length,
      nextExpiry,
      totalAvailableCredits: bucketList.reduce(
        (sum, bucket) => sum + Number(bucket.available_credits || 0),
        0,
      ),
    };
  }, [bucketList]);

  const neverExpiresLabel = t('module.billing.ledger.neverExpires');

  return (
    <Card
      className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'
      data-testid='billing-wallet-buckets-card'
    >
      <CardHeader className='space-y-2'>
        <CardTitle className='text-lg text-slate-900'>
          {t('module.billing.ledger.title')}
        </CardTitle>
        <CardDescription className='leading-6 text-slate-600'>
          {t('module.billing.ledger.bucketDescription')}
        </CardDescription>
      </CardHeader>

      <CardContent className='space-y-4'>
        {isLoading ? (
          <div className='grid gap-4 md:grid-cols-3'>
            <Skeleton className='h-24 rounded-[24px]' />
            <Skeleton className='h-24 rounded-[24px]' />
            <Skeleton className='h-24 rounded-[24px]' />
          </div>
        ) : (
          <div className='grid gap-4 md:grid-cols-3'>
            <BillingMetricCard
              label={t('module.billing.ledger.summary.totalAvailable')}
              value={formatBillingCredits(
                summary.totalAvailableCredits,
                i18n.language,
              )}
            />
            <BillingMetricCard
              label={t('module.billing.ledger.summary.activeBuckets')}
              value={String(summary.activeBucketCount)}
            />
            <BillingMetricCard
              label={t('module.billing.ledger.summary.nextExpiry')}
              value={
                summary.nextExpiry
                  ? formatBillingDate(summary.nextExpiry, i18n.language)
                  : neverExpiresLabel
              }
            />
          </div>
        )}

        {error ? (
          <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
            {t('module.billing.ledger.loadError')}
          </div>
        ) : null}

        <div className='rounded-[24px] border border-slate-200 bg-slate-50/60 px-1 py-1'>
          {isLoading ? (
            <div className='space-y-3 px-4 py-4'>
              <Skeleton className='h-12 rounded-2xl' />
              <Skeleton className='h-12 rounded-2xl' />
              <Skeleton className='h-12 rounded-2xl' />
            </div>
          ) : (
            <Table className='min-w-[720px]'>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    {t('module.billing.ledger.table.source')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.ledger.table.availableCredits')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.ledger.table.effectiveWindow')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.ledger.table.priority')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.ledger.table.status')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!bucketList.length ? (
                  <TableEmpty colSpan={5}>
                    {t('module.billing.ledger.empty')}
                  </TableEmpty>
                ) : (
                  bucketList.map(bucket => {
                    const windowLabel = renderWindowLabel(
                      bucket,
                      i18n.language,
                      resolveBillingEmptyLabel(t),
                      neverExpiresLabel,
                    );

                    return (
                      <TableRow key={bucket.wallet_bucket_bid}>
                        <TableCell className='min-w-[220px]'>
                          <div className='space-y-2'>
                            <div className='flex flex-wrap items-center gap-2'>
                              <Badge
                                variant='outline'
                                className='border-sky-200 bg-sky-50 text-sky-700'
                              >
                                {resolveBillingBucketCategoryLabel(
                                  t,
                                  bucket.category,
                                )}
                              </Badge>
                              <span className='font-medium text-slate-900'>
                                {resolveBillingBucketSourceLabel(
                                  t,
                                  bucket.source_type,
                                )}
                              </span>
                            </div>
                            <div className='text-xs text-slate-500'>
                              {bucket.source_bid}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className='font-medium text-slate-900'>
                          {formatBillingCredits(
                            bucket.available_credits,
                            i18n.language,
                          )}
                        </TableCell>
                        <TableCell className='min-w-[220px]'>
                          <div className='space-y-1 text-sm text-slate-700'>
                            <div>{windowLabel.start}</div>
                            <div className='text-xs text-slate-500'>
                              {windowLabel.end}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className='text-slate-700'>
                          {bucket.priority}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant='outline'
                            className={cn(
                              'font-medium',
                              resolveBucketStatusClasses(bucket.status),
                            )}
                          >
                            {resolveBillingBucketStatusLabel(t, bucket.status)}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export { BILLING_WALLET_BUCKETS_SWR_KEY };
