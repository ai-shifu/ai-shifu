import React, { useMemo, useState } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import type {
  BillingLedgerItem,
  BillingOrderStatus,
  BillingOrderSummary,
  BillingPagedResponse,
} from '@/types/billing';
import {
  formatBillingCredits,
  formatBillingDateTime,
  formatBillingPrice,
  registerBillingTranslationUsage,
  resolveBillingBucketSourceLabel,
  resolveBillingLedgerEntryLabel,
  resolveBillingOrderStatusLabel,
  resolveBillingOrderTypeLabel,
  resolveBillingProviderLabel,
} from '@/lib/billing';
import { BillingOrderDetailSheet } from './BillingOrderDetailSheet';
import { BillingUsageDetailSheet } from './BillingUsageDetailSheet';

const RECENT_ITEMS_LIMIT = 4;

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

function resolveOrderStatusClassName(status: BillingOrderStatus): string {
  if (status === 'paid') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (status === 'pending' || status === 'init') {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  if (status === 'failed' || status === 'canceled' || status === 'timeout') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  return 'border-slate-200 bg-slate-100 text-slate-700';
}

function ActivitySkeleton() {
  return (
    <div className='space-y-3'>
      <Skeleton className='h-24 rounded-[22px]' />
      <Skeleton className='h-24 rounded-[22px]' />
      <Skeleton className='h-24 rounded-[22px]' />
    </div>
  );
}

export function BillingRecentActivitySection() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const [selectedLedgerItem, setSelectedLedgerItem] =
    useState<BillingLedgerItem | null>(null);
  const [selectedOrderBid, setSelectedOrderBid] = useState('');
  const [orderDetailOpen, setOrderDetailOpen] = useState(false);

  const {
    data: ledgerData,
    error: ledgerError,
    isLoading: ledgerLoading,
  } = useSWR<BillingPagedResponse<BillingLedgerItem>>(
    ['billing-ledger-recent', RECENT_ITEMS_LIMIT],
    async () =>
      (await api.getBillingLedger({
        page_index: 1,
        page_size: RECENT_ITEMS_LIMIT,
      })) as BillingPagedResponse<BillingLedgerItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const {
    data: ordersData,
    error: ordersError,
    isLoading: ordersLoading,
  } = useSWR<BillingPagedResponse<BillingOrderSummary>>(
    ['billing-orders-recent', RECENT_ITEMS_LIMIT],
    async () =>
      (await api.getBillingOrders({
        page_index: 1,
        page_size: RECENT_ITEMS_LIMIT,
      })) as BillingPagedResponse<BillingOrderSummary>,
    {
      revalidateOnFocus: false,
    },
  );

  const ledgerItems = ledgerData?.items || [];
  const orderItems = ordersData?.items || [];
  const selectedHasBreakdown = useMemo(
    () => Boolean(selectedLedgerItem?.metadata.metric_breakdown?.length),
    [selectedLedgerItem],
  );

  return (
    <>
      <section className='grid gap-5 xl:grid-cols-2'>
        <Card
          id='billing-recent-ledger'
          className='rounded-[28px] border-slate-200 bg-white shadow-[0_18px_40px_rgba(15,23,42,0.08)]'
        >
          <CardHeader className='space-y-3 pb-4'>
            <div className='flex items-center justify-between gap-3'>
              <div className='space-y-1'>
                <CardTitle className='text-lg text-slate-950'>
                  {t('module.billing.ledger.title')}
                </CardTitle>
                <CardDescription className='max-w-xl text-sm leading-6 text-slate-500'>
                  {t('module.billing.ledger.entriesDescription')}
                </CardDescription>
              </div>
              <Badge
                variant='outline'
                className='rounded-full border-slate-200 bg-slate-50 px-3 py-1 text-slate-600'
              >
                {ledgerData?.total || 0}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className='space-y-3'>
            {ledgerError ? (
              <div className='rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
                {t('module.billing.ledger.loadError')}
              </div>
            ) : null}

            {ledgerLoading ? <ActivitySkeleton /> : null}

            {!ledgerLoading && !ledgerError && !ledgerItems.length ? (
              <div className='rounded-[22px] border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-sm text-slate-500'>
                {t('module.billing.ledger.empty')}
              </div>
            ) : null}

            {!ledgerLoading &&
              !ledgerError &&
              ledgerItems.map(item => (
                <div
                  key={item.ledger_bid}
                  className='rounded-[24px] border border-slate-200 bg-slate-50/70 p-4'
                >
                  <div className='flex items-start justify-between gap-4'>
                    <div className='space-y-2'>
                      <div className='flex flex-wrap items-center gap-2'>
                        <Badge
                          variant='outline'
                          className='border-slate-200 bg-white text-slate-700'
                        >
                          {resolveBillingLedgerEntryLabel(t, item.entry_type)}
                        </Badge>
                        <span className='text-sm text-slate-500'>
                          {resolveBillingBucketSourceLabel(t, item.source_type)}
                        </span>
                      </div>
                      <div className='text-sm text-slate-500'>
                        {item.source_bid}
                      </div>
                      <div className='text-xs text-slate-400'>
                        {formatBillingDateTime(item.created_at, i18n.language)}
                      </div>
                    </div>
                    <div className='flex flex-col items-end gap-3'>
                      <div className='text-right'>
                        <div className='text-base font-semibold text-slate-950 md:text-lg'>
                          {formatSignedCredits(item.amount, i18n.language)}
                        </div>
                        <div className='flex items-center justify-end gap-1 text-xs text-slate-500'>
                          <span>
                            {t('module.billing.ledger.table.balanceAfter')}
                          </span>
                          <span>
                            {formatBillingCredits(
                              item.balance_after,
                              i18n.language,
                            )}
                          </span>
                        </div>
                      </div>
                      {item.metadata.metric_breakdown?.length ? (
                        <Button
                          variant='outline'
                          size='sm'
                          className='rounded-full'
                          onClick={() => setSelectedLedgerItem(item)}
                        >
                          {t('module.billing.ledger.table.detail')}
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>

        <Card
          id='billing-recent-orders'
          className='rounded-[28px] border-slate-200 bg-white shadow-[0_18px_40px_rgba(15,23,42,0.08)]'
        >
          <CardHeader className='space-y-3 pb-4'>
            <div className='flex items-center justify-between gap-3'>
              <div className='space-y-1'>
                <CardTitle className='text-lg text-slate-950'>
                  {t('module.billing.orders.title')}
                </CardTitle>
                <CardDescription className='max-w-xl text-sm leading-6 text-slate-500'>
                  {t('module.billing.orders.description')}
                </CardDescription>
              </div>
              <Badge
                variant='outline'
                className='rounded-full border-slate-200 bg-slate-50 px-3 py-1 text-slate-600'
              >
                {ordersData?.total || 0}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className='space-y-3'>
            {ordersError ? (
              <div className='rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
                {t('module.billing.orders.loadError')}
              </div>
            ) : null}

            {ordersLoading ? <ActivitySkeleton /> : null}

            {!ordersLoading && !ordersError && !orderItems.length ? (
              <div className='rounded-[22px] border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-sm text-slate-500'>
                {t('module.billing.orders.empty')}
              </div>
            ) : null}

            {!ordersLoading &&
              !ordersError &&
              orderItems.map(item => (
                <div
                  key={item.billing_order_bid}
                  className='rounded-[24px] border border-slate-200 bg-slate-50/70 p-4'
                >
                  <div className='flex items-start justify-between gap-4'>
                    <div className='space-y-2'>
                      <div className='flex flex-wrap items-center gap-2'>
                        <Button
                          variant='link'
                          size='sm'
                          className='h-auto p-0 text-left text-sm font-semibold text-slate-950 no-underline hover:text-slate-950 hover:no-underline md:text-base'
                          onClick={() => {
                            setSelectedOrderBid(item.billing_order_bid);
                            setOrderDetailOpen(true);
                          }}
                        >
                          {resolveBillingOrderTypeLabel(t, item.order_type)}
                        </Button>
                        <Badge
                          variant='outline'
                          className={resolveOrderStatusClassName(item.status)}
                        >
                          {resolveBillingOrderStatusLabel(t, item.status)}
                        </Badge>
                      </div>
                      <div className='text-sm text-slate-500'>
                        {resolveBillingProviderLabel(t, item.payment_provider)}
                      </div>
                      <div className='text-xs text-slate-400'>
                        {item.failure_message || item.provider_reference_id}
                      </div>
                    </div>
                    <div className='flex flex-col items-end gap-3'>
                      <div className='text-right'>
                        <div className='text-base font-semibold text-slate-950 md:text-lg'>
                          {formatBillingPrice(
                            item.paid_amount || item.payable_amount,
                            item.currency,
                            i18n.language,
                          )}
                        </div>
                        <div className='text-xs text-slate-500'>
                          {formatBillingDateTime(
                            item.created_at,
                            i18n.language,
                          )}
                        </div>
                      </div>
                      <Button
                        variant='outline'
                        size='sm'
                        className='rounded-full'
                        onClick={() => {
                          setSelectedOrderBid(item.billing_order_bid);
                          setOrderDetailOpen(true);
                        }}
                      >
                        {t('module.billing.orders.table.order')}
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>
      </section>

      <BillingUsageDetailSheet
        item={selectedHasBreakdown ? selectedLedgerItem : null}
        open={Boolean(selectedLedgerItem && selectedHasBreakdown)}
        onOpenChange={open => {
          if (!open) {
            setSelectedLedgerItem(null);
          }
        }}
      />

      <BillingOrderDetailSheet
        open={orderDetailOpen}
        orderBid={selectedOrderBid || undefined}
        onOpenChange={open => {
          setOrderDetailOpen(open);
          if (!open) {
            setSelectedOrderBid('');
          }
        }}
      />
    </>
  );
}
