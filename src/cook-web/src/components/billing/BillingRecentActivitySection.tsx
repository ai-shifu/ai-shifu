import React from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { Card, CardContent } from '@/components/ui/Card';
import { AppPagination } from '@/components/pagination/AppPagination';
import { Skeleton } from '@/components/ui/Skeleton';
import type { BillingLedgerItem, BillingPagedResponse } from '@/types/billing';
import {
  buildBillingSwrKey,
  formatBillingCredits,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingLedgerReasonLabel,
  withBillingTimezone,
} from '@/lib/billing';

const RECENT_ITEMS_LIMIT = 10;

function formatSignedCredits(value: number, locale: string): string {
  const normalizedValue = Number(value || 0);
  const formatted = formatBillingCredits(Math.abs(normalizedValue), locale);
  if (normalizedValue > 0) {
    return `+${formatted}`;
  }
  if (normalizedValue < 0) {
    return `-${formatted}`;
  }
  return formatted;
}

function UsageTableSkeleton() {
  return (
    <div data-testid='billing-usage-table-skeleton'>
      {Array.from({ length: RECENT_ITEMS_LIMIT }, (_, index) => (
        <div
          key={`billing-usage-skeleton-row-${index}`}
          data-testid='billing-usage-skeleton-row'
          className='grid grid-cols-[1.6fr_0.9fr_0.7fr] border-b border-[var(--base-border,#E5E5E5)] last:border-b-0'
        >
          <div className='px-[32px] py-4 pl-[32px] pr-[var(--spacing-2,8px)]'>
            <Skeleton className='h-5 w-full rounded-md' />
          </div>
          <div className='px-[32px] py-4 pl-[var(--spacing-2,8px)] pr-[32px]'>
            <Skeleton className='ml-auto h-5 w-32 rounded-md' />
          </div>
          <div className='px-[32px] py-4 pl-[8px] pr-[32px]'>
            <Skeleton className='ml-auto h-5 w-20 rounded-md' />
          </div>
        </div>
      ))}
    </div>
  );
}

export function BillingRecentActivitySection() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const timezone = getBrowserTimeZone();
  const [pageIndex, setPageIndex] = React.useState(1);

  const {
    data: ledgerData,
    error: ledgerError,
    isLoading: ledgerLoading,
  } = useSWR<BillingPagedResponse<BillingLedgerItem>>(
    buildBillingSwrKey(
      'billing-ledger-recent',
      timezone,
      pageIndex,
      RECENT_ITEMS_LIMIT,
    ),
    async () =>
      (await api.getBillingLedger({
        ...withBillingTimezone(
          {
            page_index: pageIndex,
            page_size: RECENT_ITEMS_LIMIT,
          },
          timezone,
        ),
      })) as BillingPagedResponse<BillingLedgerItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const ledgerItems = ledgerData?.items || [];
  const pageCount = Number(ledgerData?.page_count || 1);
  const currentPage = Number(ledgerData?.page || pageIndex);

  return (
    <section
      id='billing-recent-orders'
      className='space-y-4'
      data-testid='billing-usage-table-section'
    >
      <div>
        <h2 className='text-xl font-semibold tracking-tight text-slate-950 md:text-2xl'>
          {t('module.billing.details.usageTable.title')}
        </h2>
      </div>

      <Card
        className='overflow-hidden rounded-[var(--border-radius-rounded-lg,10px)] border border-[var(--base-border,#E5E5E5)] bg-[var(--base-card,#FFF)] shadow-[var(--shadow-xs-offset-x,0)_var(--shadow-xs-offset-y,1px)_var(--shadow-xs-blur-radius,2px)_var(--shadow-xs-spread-radius,0)_var(--shadow-xs-color,rgba(0,0,0,0.05))]'
        data-testid='billing-usage-table-card'
      >
        <CardContent className='p-0'>
          {ledgerError ? (
            <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
              {t('module.billing.ledger.loadError')}
            </div>
          ) : null}

          {!ledgerError ? (
            <div
              className='overflow-auto'
              data-testid='billing-usage-table-scroll'
            >
              <div className='min-w-[720px]'>
                <div className='grid grid-cols-[1.6fr_0.9fr_0.7fr] border-b border-[var(--base-border,#E5E5E5)] bg-[var(--base-muted,#F5F5F5)]'>
                  <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center gap-[10px] px-[32px] pl-[32px] pr-[var(--spacing-2,8px)] text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                    {t('module.billing.details.usageTable.columns.scene')}
                  </div>
                  <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center justify-end px-[32px] pl-[var(--spacing-2,8px)] pr-[32px] text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                    {t('module.billing.ledger.table.createdAt')}
                  </div>
                  <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center justify-end px-[32px] pl-[8px] pr-[32px] text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                    {t('module.billing.ledger.table.amount')}
                  </div>
                </div>

                {ledgerLoading ? <UsageTableSkeleton /> : null}

                {!ledgerLoading && !ledgerItems.length ? (
                  <div className='px-4 py-8 text-sm text-slate-500'>
                    {t('module.billing.ledger.empty')}
                  </div>
                ) : null}

                {!ledgerLoading &&
                  ledgerItems.map(item => (
                    <div
                      key={item.ledger_bid}
                      className='grid grid-cols-[1.6fr_0.9fr_0.7fr] border-b border-[var(--base-border,#E5E5E5)] last:border-b-0'
                    >
                      <div className='overflow-hidden px-[32px] py-4 pl-[32px] pr-[var(--spacing-2,8px)] text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                        {resolveBillingLedgerReasonLabel(t, item)}
                      </div>
                      <div className='overflow-hidden px-[32px] py-4 pl-[var(--spacing-2,8px)] pr-[32px] text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                        {formatBillingDateTime(item.created_at, i18n.language)}
                      </div>
                      <div className='overflow-hidden px-[32px] py-4 pl-[8px] pr-[32px] text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                        {formatSignedCredits(item.amount, i18n.language)}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          ) : null}
          {!ledgerError && pageCount > 1 ? (
            <div className='px-6 py-4'>
              <AppPagination
                pageIndex={currentPage}
                pageCount={pageCount}
                onPageChange={setPageIndex}
                prevLabel={t('module.order.paginationPrev')}
                nextLabel={t('module.order.paginationNext')}
                prevAriaLabel={t(
                  'module.order.paginationPrevAriaLabel',
                  'Go to previous page',
                )}
                nextAriaLabel={t(
                  'module.order.paginationNextAriaLabel',
                  'Go to next page',
                )}
                className='mx-0 w-full justify-end'
                hideWhenSinglePage
              />
            </div>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
