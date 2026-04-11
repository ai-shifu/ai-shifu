import React from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';
import { Skeleton } from '@/components/ui/Skeleton';
import type {
  BillingLedgerItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  formatBillingCredits,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
  resolveBillingUsageSceneLabel,
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
    <div className='space-y-3 px-2 py-4'>
      <Skeleton className='h-10 rounded-xl' />
      <Skeleton className='h-10 rounded-xl' />
      <Skeleton className='h-10 rounded-xl' />
    </div>
  );
}

export function BillingRecentActivitySection() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const [pageIndex, setPageIndex] = React.useState(1);

  const {
    data: ledgerData,
    error: ledgerError,
    isLoading: ledgerLoading,
  } = useSWR<BillingPagedResponse<BillingLedgerItem>>(
    ['billing-ledger-recent', pageIndex, RECENT_ITEMS_LIMIT],
    async () =>
      (await api.getBillingLedger({
        page_index: pageIndex,
        page_size: RECENT_ITEMS_LIMIT,
      })) as BillingPagedResponse<BillingLedgerItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const ledgerItems = ledgerData?.items || [];
  const pageCount = Number(ledgerData?.page_count || 1);
  const total = Number(ledgerData?.total || 0);
  const currentPage = Number(ledgerData?.page || pageIndex);
  const canGoPrev = currentPage > 1;
  const canGoNext = currentPage < pageCount;

  const paginationItems = Array.from({ length: pageCount }, (_, index) => {
    const page = index + 1;

    return (
      <PaginationItem key={page}>
        <PaginationLink
          href='#'
          isActive={page === currentPage}
          onClick={event => {
            event.preventDefault();
            setPageIndex(page);
          }}
          size='icon'
        >
          {page}
        </PaginationLink>
      </PaginationItem>
    );
  });

  return (
    <section
      id='billing-recent-orders'
      className='space-y-4'
      data-testid='billing-usage-table-section'
    >
      <Card className='overflow-hidden rounded-[var(--border-radius-rounded-lg,10px)] border border-[var(--base-border,#E5E5E5)] bg-[var(--base-card,#FFF)] shadow-[var(--shadow-xs-offset-x,0)_var(--shadow-xs-offset-y,1px)_var(--shadow-xs-blur-radius,2px)_var(--shadow-xs-spread-radius,0)_var(--shadow-xs-color,rgba(0,0,0,0.05))]'>
        <CardContent className='p-0'>
          {ledgerError ? (
            <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
              {t('module.billing.ledger.loadError')}
            </div>
          ) : null}

          {!ledgerError ? (
            <div>
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
                      {resolveBillingUsageSceneLabel(
                        t,
                        item.metadata.usage_scene,
                      ) || resolveBillingEmptyLabel(t)}
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
          ) : null}
        </CardContent>
      </Card>

      {pageCount > 1 ? (
        <Pagination className='mx-0 w-full justify-end'>
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href='#'
                aria-disabled={!canGoPrev}
                className={!canGoPrev ? 'pointer-events-none opacity-50' : ''}
                onClick={event => {
                  event.preventDefault();
                  if (canGoPrev) {
                    setPageIndex(current => Math.max(1, current - 1));
                  }
                }}
              >
                {t('module.order.paginationPrev')}
              </PaginationPrevious>
            </PaginationItem>
            {paginationItems}
            <PaginationItem>
              <PaginationNext
                href='#'
                aria-disabled={!canGoNext}
                className={!canGoNext ? 'pointer-events-none opacity-50' : ''}
                onClick={event => {
                  event.preventDefault();
                  if (canGoNext) {
                    setPageIndex(current => Math.min(pageCount, current + 1));
                  }
                }}
              >
                {t('module.order.paginationNext')}
              </PaginationNext>
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      ) : null}
    </section>
  );
}
