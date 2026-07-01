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
import { BILLING_SECTION_TITLE_CLASS } from '@/components/billing/billingSectionTitleClass';
import {
  buildBillingSwrKey,
  formatBillingCreditDetail,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingLedgerReasonLabel,
} from '@/lib/billing';

const RECENT_ITEMS_LIMIT = 10;
const USAGE_TABLE_HEADER_HEIGHT = 40;
const USAGE_TABLE_ROW_HEIGHT = 53;
const USAGE_TABLE_PAGE_MIN_HEIGHT =
  USAGE_TABLE_HEADER_HEIGHT + RECENT_ITEMS_LIMIT * USAGE_TABLE_ROW_HEIGHT;

type BillingRecentActivitySectionProps = {
  className?: string;
  stretchToFill?: boolean;
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
  stretchToFill = false,
}: BillingRecentActivitySectionProps) {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const [pageIndex, setPageIndex] = React.useState(1);

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
  const pageCount = Number(ledgerData?.page_count || 1);
  const currentPage = Number(ledgerData?.page || pageIndex);
  const shouldUsePageHeight =
    ledgerLoading || ledgerItems.length >= RECENT_ITEMS_LIMIT;
  const shouldStretchTable = stretchToFill && shouldUsePageHeight;
  const usageTablePageStyle: React.CSSProperties | undefined =
    shouldUsePageHeight
      ? {
          minHeight: USAGE_TABLE_PAGE_MIN_HEIGHT,
        }
      : undefined;

  return (
    <section
      id='billing-recent-orders'
      className={cn(
        stretchToFill ? 'flex min-h-0 flex-col gap-6' : 'space-y-6',
        className,
      )}
      data-testid='billing-usage-table-section'
    >
      <div>
        <h2 className={BILLING_SECTION_TITLE_CLASS}>
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
          containerClassName={cn(stretchToFill && 'min-h-0 flex-1')}
          tableWrapperClassName={cn(
            'overflow-hidden rounded-[var(--border-radius-rounded-lg,10px)] [&_tbody_tr[data-admin-skeleton-row]:hover]:!bg-transparent [&_tbody_tr[data-admin-skeleton-row]:hover_td]:!bg-transparent',
            shouldStretchTable && 'flex min-h-0 flex-1 flex-col',
          )}
          tableWrapperStyle={usageTablePageStyle}
          footerClassName='px-0'
          pagination={
            pageCount > 1
              ? {
                  pageIndex: currentPage,
                  pageCount,
                  onPageChange: setPageIndex,
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
              className={cn(
                'overflow-auto',
                shouldStretchTable && 'min-h-0 flex-1',
              )}
              style={usageTablePageStyle}
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
