import React, { useMemo, useState } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
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
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import type { BillingLedgerItem, BillingPagedResponse } from '@/types/billing';
import {
  formatBillingCredits,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingBucketSourceLabel,
  resolveBillingLedgerEntryLabel,
  resolveBillingLedgerReasonLabel,
} from '@/lib/billing';
import { BillingUsageDetailSheet } from './BillingUsageDetailSheet';

const BILLING_LEDGER_PAGE_SIZE = 10;

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

export function BillingLedgerTable() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const [pageIndex, setPageIndex] = useState(1);
  const [selectedItem, setSelectedItem] = useState<BillingLedgerItem | null>(
    null,
  );
  const { data, error, isLoading } = useSWR<
    BillingPagedResponse<BillingLedgerItem>
  >(
    ['billing-ledger', pageIndex, BILLING_LEDGER_PAGE_SIZE],
    async () =>
      (await api.getBillingLedger({
        page_index: pageIndex,
        page_size: BILLING_LEDGER_PAGE_SIZE,
      })) as BillingPagedResponse<BillingLedgerItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const items = data?.items || [];
  const canGoPrev = pageIndex > 1;
  const canGoNext = pageIndex < Number(data?.page_count || 1);
  const selectedHasBreakdown = useMemo(
    () => Boolean(selectedItem?.metadata.metric_breakdown?.length),
    [selectedItem],
  );

  return (
    <>
      <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
        <CardHeader className='space-y-2'>
          <CardTitle className='text-lg text-slate-900'>
            {t('module.billing.ledger.entriesTitle')}
          </CardTitle>
          <CardDescription className='leading-6 text-slate-600'>
            {t('module.billing.ledger.entriesDescription')}
          </CardDescription>
        </CardHeader>

        <CardContent className='space-y-4'>
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
              <Table className='min-w-[920px]'>
                <TableHeader>
                  <TableRow>
                    <TableHead>
                      {t('module.billing.ledger.table.entryType')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.ledger.table.source')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.ledger.table.amount')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.ledger.table.balanceAfter')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.ledger.table.createdAt')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.ledger.table.action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {!items.length ? (
                    <TableEmpty colSpan={6}>
                      {t('module.billing.ledger.empty')}
                    </TableEmpty>
                  ) : (
                    items.map(item => {
                      const sourceLabel = resolveBillingBucketSourceLabel(
                        t,
                        item.source_type,
                      );
                      const reasonLabel = resolveBillingLedgerReasonLabel(
                        t,
                        item,
                      );

                      return (
                        <TableRow key={item.ledger_bid}>
                          <TableCell className='min-w-[180px]'>
                            <Badge
                              variant='outline'
                              className='border-slate-200 bg-white text-slate-700'
                            >
                              {resolveBillingLedgerEntryLabel(
                                t,
                                item.entry_type,
                              )}
                            </Badge>
                          </TableCell>
                          <TableCell className='min-w-[220px]'>
                            <div className='space-y-1'>
                              <div className='font-medium text-slate-900'>
                                {sourceLabel}
                              </div>
                              {reasonLabel !== sourceLabel ? (
                                <div className='text-xs text-slate-600'>
                                  {reasonLabel}
                                </div>
                              ) : null}
                              <div className='text-xs text-slate-500'>
                                {item.source_bid}
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className='font-medium text-slate-900'>
                            {formatSignedCredits(item.amount, i18n.language)}
                          </TableCell>
                          <TableCell>
                            {formatBillingCredits(
                              item.balance_after,
                              i18n.language,
                            )}
                          </TableCell>
                          <TableCell className='min-w-[180px] text-slate-600'>
                            {formatBillingDateTime(
                              item.created_at,
                              i18n.language,
                            )}
                          </TableCell>
                          <TableCell>
                            {item.metadata.metric_breakdown?.length ? (
                              <Button
                                variant='outline'
                                size='sm'
                                onClick={() => setSelectedItem(item)}
                              >
                                {t('module.billing.ledger.table.detail')}
                              </Button>
                            ) : null}
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            )}
          </div>

          <div className='flex flex-wrap items-center justify-between gap-3'>
            <div className='text-sm text-slate-500'>
              {t('module.billing.ledger.pagination.page', {
                page: data?.page || pageIndex,
                pageCount: data?.page_count || 1,
                total: data?.total || 0,
              })}
            </div>
            <div className='flex gap-2'>
              <Button
                variant='outline'
                disabled={!canGoPrev}
                onClick={() =>
                  setPageIndex(current => Math.max(1, current - 1))
                }
              >
                {t('common.page.previous')}
              </Button>
              <Button
                variant='outline'
                disabled={!canGoNext}
                onClick={() =>
                  setPageIndex(current =>
                    Math.min(Number(data?.page_count || current), current + 1),
                  )
                }
              >
                {t('common.page.next')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <BillingUsageDetailSheet
        item={selectedHasBreakdown ? selectedItem : null}
        open={Boolean(selectedItem && selectedHasBreakdown)}
        onOpenChange={open => {
          if (!open) {
            setSelectedItem(null);
          }
        }}
      />
    </>
  );
}
