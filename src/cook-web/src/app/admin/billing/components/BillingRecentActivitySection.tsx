import React from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Skeleton } from '@/components/ui/Skeleton';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import type { BillingLedgerItem, BillingPagedResponse } from '@/types/billing';
import { BILLING_SUBSECTION_TITLE_CLASS } from '@/components/billing/billingSectionTitleClass';
import {
  buildBillingSwrKey,
  formatBillingCreditDetail,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingLedgerReasonLabel,
} from '@/lib/billing';

const RECENT_ITEMS_LIMIT = 20;

type BillingRecentActivitySectionProps = {
  className?: string;
};

function formatSignedCredits(value: number, locale: string): string {
  const normalizedValue = Number(value || 0);
  const formatted = formatBillingCreditDetail(
    Math.abs(normalizedValue),
    locale,
  );
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
    <>
      {Array.from({ length: RECENT_ITEMS_LIMIT }, (_, index) => (
        <TableRow
          key={`billing-usage-skeleton-row-${index}`}
          className='hover:!bg-transparent data-[state=selected]:!bg-transparent'
          data-admin-skeleton-row='true'
          data-testid='billing-usage-skeleton-row'
        >
          <TableCell
            data-testid={
              index === 0 ? 'billing-usage-table-skeleton' : undefined
            }
          >
            <Skeleton className='h-5 w-full rounded-md' />
          </TableCell>
          <TableCell>
            <Skeleton className='h-5 w-32 rounded-md' />
          </TableCell>
          <TableCell>
            <Skeleton className='ml-auto h-5 w-20 rounded-md' />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

export function BillingRecentActivitySection({
  className,
}: BillingRecentActivitySectionProps) {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const sectionRef = React.useRef<HTMLElement | null>(null);
  const headingRef = React.useRef<HTMLHeadingElement | null>(null);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(1);
  const lastPageIndexRef = React.useRef(pageIndex);

  const {
    data: ledgerData,
    error: ledgerError,
    isLoading: ledgerLoading,
  } = useSWR<BillingPagedResponse<BillingLedgerItem>>(
    buildBillingSwrKey('billing-ledger-recent', pageIndex, RECENT_ITEMS_LIMIT),
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
  const ledgerPageCount = Number(ledgerData?.page_count || 1);
  const currentPage = Number(ledgerData?.page || pageIndex);
  React.useEffect(() => {
    if (ledgerData) {
      setPageCount(ledgerPageCount);
    }
  }, [ledgerData, ledgerPageCount]);
  React.useEffect(() => {
    if (lastPageIndexRef.current === pageIndex) {
      return;
    }
    lastPageIndexRef.current = pageIndex;
    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    sectionRef.current?.scrollIntoView?.({
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
      block: 'start',
    });
    headingRef.current?.focus({ preventScroll: true });
  }, [pageIndex]);
  const handlePageChange = React.useCallback((nextPage: number) => {
    setPageIndex(nextPage);
  }, []);

  return (
    <section
      ref={sectionRef}
      id='billing-recent-orders'
      className={cn('space-y-6', className)}
      data-testid='billing-usage-table-section'
    >
      <div>
        <h2
          ref={headingRef}
          tabIndex={-1}
          className={cn(
            BILLING_SUBSECTION_TITLE_CLASS,
            'rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2',
          )}
        >
          {t('module.billing.details.usageTable.title')}
        </h2>
      </div>

      {ledgerError ? (
        <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
          {t('module.billing.ledger.loadError')}
        </div>
      ) : (
        <AdminTableShell
          loading={false}
          isEmpty={!ledgerLoading && ledgerItems.length === 0}
          emptyContent={t('module.billing.ledger.empty')}
          emptyColSpan={3}
          tableWrapperClassName='overflow-hidden rounded-[var(--border-radius-rounded-lg,10px)] [&_tbody_tr[data-admin-skeleton-row]:hover]:!bg-transparent [&_tbody_tr[data-admin-skeleton-row]:hover_td]:!bg-transparent'
          footerClassName='px-0'
          pagination={
            pageCount > 1
              ? {
                  pageIndex: currentPage,
                  pageCount,
                  onPageChange: handlePageChange,
                  prevLabel: t('module.order.paginationPrev'),
                  nextLabel: t('module.order.paginationNext'),
                  prevAriaLabel: t(
                    'module.order.paginationPrevAriaLabel',
                    'Go to previous page',
                  ),
                  nextAriaLabel: t(
                    'module.order.paginationNextAriaLabel',
                    'Go to next page',
                  ),
                  hideWhenSinglePage: true,
                }
              : undefined
          }
          table={emptyRow => (
            <div
              className='overflow-x-auto'
              data-testid='billing-usage-table-scroll'
            >
              <Table
                className='min-w-[720px] table-fixed'
                containerClassName='overflow-visible'
              >
                <colgroup>
                  <col className='w-[64%]' />
                  <col className='w-[24%]' />
                  <col className='w-[12%]' />
                </colgroup>
                <TableHeader>
                  <TableRow>
                    <TableHead>
                      {t('module.billing.details.usageTable.columns.scene')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.ledger.table.createdAt')}
                    </TableHead>
                    <TableHead>
                      <div className='flex justify-end'>
                        {t('module.billing.ledger.table.amount')}
                      </div>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ledgerLoading ? <UsageTableSkeleton /> : emptyRow}
                  {!ledgerLoading &&
                    ledgerItems.map(item => (
                      <TableRow key={item.ledger_bid}>
                        <TableCell>
                          {resolveBillingLedgerReasonLabel(t, item)}
                        </TableCell>
                        <TableCell>
                          {formatBillingDateTime(
                            item.created_at,
                            i18n.language,
                          )}
                        </TableCell>
                        <TableCell>
                          <div className='flex justify-end'>
                            {formatSignedCredits(item.amount, i18n.language)}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </div>
          )}
        />
      )}
    </section>
  );
}
