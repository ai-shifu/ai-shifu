import React, { useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
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
import { toast } from '@/hooks/useToast';
import type {
  BillingCheckoutResult,
  BillingOrderStatus,
  BillingOrderSummary,
  BillingPingxxChannel,
  BillingPagedResponse,
} from '@/types/billing';
import {
  buildBillingSwrKey,
  extractBillingPingxxQrCode,
  formatBillingDateTime,
  formatBillingPrice,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
  resolveBillingOrderStatusLabel,
  resolveBillingOrderTypeLabel,
  resolveBillingProviderLabel,
  withBillingTimezone,
} from '@/lib/billing';
import { useBillingPingxxPolling } from '@/hooks/useBillingPingxxPolling';
import { BillingOrderDetailSheet } from './BillingOrderDetailSheet';
import { BillingPingxxQrDialog } from './BillingPingxxQrDialog';

const BILLING_ORDERS_PAGE_SIZE = 10;

function canContinueBillingOrderCheckout(order: BillingOrderSummary): boolean {
  return (
    order.payment_provider === 'pingxx' &&
    order.status === 'pending' &&
    (order.order_type === 'subscription_start' ||
      order.order_type === 'subscription_renewal')
  );
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

export function BillingOrdersTable() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const timezone = getBrowserTimeZone();
  const [pageIndex, setPageIndex] = useState(1);
  const [syncLoadingBid, setSyncLoadingBid] = useState('');
  const [checkoutLoadingBid, setCheckoutLoadingBid] = useState('');
  const [pingxxCheckoutOrder, setPingxxCheckoutOrder] =
    useState<BillingOrderSummary | null>(null);
  const [selectedPingxxChannel, setSelectedPingxxChannel] =
    useState<BillingPingxxChannel>('wx_pub_qr');
  const [pingxxQrUrl, setPingxxQrUrl] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailOrderBid, setDetailOrderBid] = useState('');
  const { mutate: mutateCache } = useSWRConfig();
  const { data, error, isLoading, mutate } = useSWR<
    BillingPagedResponse<BillingOrderSummary>
  >(
    buildBillingSwrKey(
      'billing-orders',
      timezone,
      pageIndex,
      BILLING_ORDERS_PAGE_SIZE,
    ),
    async () =>
      (await api.getBillingOrders({
        ...withBillingTimezone(
          {
            page_index: pageIndex,
            page_size: BILLING_ORDERS_PAGE_SIZE,
          },
          timezone,
        ),
      })) as BillingPagedResponse<BillingOrderSummary>,
    {
      revalidateOnFocus: false,
    },
  );

  const items = data?.items || [];
  const canGoPrev = pageIndex > 1;
  const canGoNext = pageIndex < Number(data?.page_count || 1);

  useBillingPingxxPolling({
    open: Boolean(pingxxCheckoutOrder),
    billingOrderBid: pingxxCheckoutOrder?.billing_order_bid || '',
    onResolved: async result => {
      await mutate();
      if (detailOrderBid === result.billing_order_bid) {
        await mutateCache(
          buildBillingSwrKey(
            'billing-order-detail',
            timezone,
            result.billing_order_bid,
          ),
        );
      }
      if (result.status !== 'pending') {
        setPingxxCheckoutOrder(null);
        setPingxxQrUrl('');
      }
    },
  });

  const handleSync = async (order: BillingOrderSummary) => {
    setSyncLoadingBid(order.billing_order_bid);
    try {
      const result = (await api.syncBillingOrder({
        billing_order_bid: order.billing_order_bid,
      })) as { billing_order_bid: string; status: BillingOrderStatus };
      await mutate();
      if (detailOrderBid === order.billing_order_bid) {
        await mutateCache(
          buildBillingSwrKey(
            'billing-order-detail',
            timezone,
            order.billing_order_bid,
          ),
        );
      }
      toast({
        title: t('module.billing.orders.syncSuccess', {
          status: resolveBillingOrderStatusLabel(t, result.status),
        }),
      });
    } catch (error: any) {
      toast({
        title: error?.message || t('common.core.unknownError'),
        variant: 'destructive',
      });
    } finally {
      setSyncLoadingBid('');
    }
  };

  const handleOpenDetail = (billingOrderBid: string) => {
    setDetailOrderBid(billingOrderBid);
    setDetailOpen(true);
  };

  const handleContinueCheckout = async (
    order: BillingOrderSummary,
    channel: BillingPingxxChannel = 'wx_pub_qr',
  ) => {
    setCheckoutLoadingBid(order.billing_order_bid);
    try {
      const result = (await api.checkoutBillingOrder({
        billing_order_bid: order.billing_order_bid,
        channel,
      })) as BillingCheckoutResult;
      const qrCode = extractBillingPingxxQrCode(result, channel);
      if (!qrCode) {
        toast({
          title: t('module.billing.checkout.unsupported'),
          variant: 'destructive',
        });
        return;
      }
      setSelectedPingxxChannel(qrCode.channel);
      setPingxxQrUrl(qrCode.url);
      setPingxxCheckoutOrder(order);
    } catch (error: any) {
      toast({
        title: error?.message || t('common.core.unknownError'),
        variant: 'destructive',
      });
    } finally {
      setCheckoutLoadingBid('');
    }
  };

  return (
    <>
      <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
        <CardHeader className='space-y-2'>
          <CardTitle className='text-base text-slate-900 md:text-lg'>
            {t('module.billing.orders.title')}
          </CardTitle>
          <CardDescription className='leading-6 text-slate-600'>
            {t('module.billing.orders.description')}
          </CardDescription>
        </CardHeader>

        <CardContent className='space-y-4'>
          {error ? (
            <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
              {t('module.billing.orders.loadError')}
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
              <Table className='min-w-[960px]'>
                <TableHeader>
                  <TableRow>
                    <TableHead>
                      {t('module.billing.orders.table.order')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.orders.table.provider')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.orders.table.status')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.orders.table.amount')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.orders.table.createdAt')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.orders.table.failure')}
                    </TableHead>
                    <TableHead>
                      {t('module.billing.orders.table.actions')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {!items.length ? (
                    <TableEmpty colSpan={7}>
                      {t('module.billing.orders.empty')}
                    </TableEmpty>
                  ) : (
                    items.map(item => (
                      <TableRow key={item.billing_order_bid}>
                        <TableCell className='min-w-[220px]'>
                          <div className='space-y-1'>
                            <Button
                              variant='link'
                              size='sm'
                              className='h-auto justify-start p-0 text-left font-medium text-slate-900 no-underline hover:text-slate-900 hover:no-underline'
                              onClick={() =>
                                handleOpenDetail(item.billing_order_bid)
                              }
                            >
                              {resolveBillingOrderTypeLabel(t, item.order_type)}
                            </Button>
                            <div className='text-xs text-slate-500'>
                              {item.billing_order_bid}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className='min-w-[180px]'>
                          {resolveBillingProviderLabel(
                            t,
                            item.payment_provider,
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant='outline'
                            className={resolveOrderStatusClassName(item.status)}
                          >
                            {resolveBillingOrderStatusLabel(t, item.status)}
                          </Badge>
                        </TableCell>
                        <TableCell className='font-medium text-slate-900'>
                          {formatBillingPrice(
                            item.paid_amount || item.payable_amount,
                            item.currency,
                            i18n.language,
                          )}
                        </TableCell>
                        <TableCell className='min-w-[180px] text-slate-600'>
                          {formatBillingDateTime(
                            item.created_at,
                            i18n.language,
                          )}
                        </TableCell>
                        <TableCell className='min-w-[180px] text-sm text-slate-500'>
                          {item.failure_message || resolveBillingEmptyLabel(t)}
                        </TableCell>
                        <TableCell>
                          <div className='flex flex-wrap gap-2'>
                            {canContinueBillingOrderCheckout(item) ? (
                              <Button
                                variant='default'
                                size='sm'
                                disabled={
                                  checkoutLoadingBid === item.billing_order_bid
                                }
                                onClick={() =>
                                  void handleContinueCheckout(item)
                                }
                              >
                                {checkoutLoadingBid === item.billing_order_bid
                                  ? t(
                                      'module.billing.catalog.actions.processing',
                                    )
                                  : t(
                                      'module.billing.orders.actions.continuePayment',
                                    )}
                              </Button>
                            ) : null}
                            <Button
                              variant='outline'
                              size='sm'
                              disabled={
                                syncLoadingBid === item.billing_order_bid
                              }
                              onClick={() => void handleSync(item)}
                            >
                              {syncLoadingBid === item.billing_order_bid
                                ? t('module.billing.catalog.actions.processing')
                                : t('module.billing.orders.actions.sync')}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            )}
          </div>

          <div className='flex flex-wrap items-center justify-between gap-3'>
            <div className='text-sm text-slate-500'>
              {t('module.billing.orders.pagination.page', {
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

      <BillingOrderDetailSheet
        open={detailOpen}
        orderBid={detailOrderBid}
        onOpenChange={open => {
          setDetailOpen(open);
          if (!open) {
            setDetailOrderBid('');
          }
        }}
      />
      <BillingPingxxQrDialog
        amountInMinor={
          pingxxCheckoutOrder
            ? pingxxCheckoutOrder.paid_amount ||
              pingxxCheckoutOrder.payable_amount
            : 0
        }
        currency={pingxxCheckoutOrder?.currency || 'CNY'}
        description=''
        isLoading={
          Boolean(checkoutLoadingBid) &&
          checkoutLoadingBid === pingxxCheckoutOrder?.billing_order_bid
        }
        open={Boolean(pingxxCheckoutOrder)}
        productName={
          pingxxCheckoutOrder
            ? resolveBillingOrderTypeLabel(t, pingxxCheckoutOrder.order_type)
            : ''
        }
        qrUrl={pingxxQrUrl}
        selectedChannel={selectedPingxxChannel}
        onChannelChange={channel => {
          if (pingxxCheckoutOrder) {
            void handleContinueCheckout(pingxxCheckoutOrder, channel);
          }
        }}
        onOpenChange={open => {
          if (!open) {
            setPingxxCheckoutOrder(null);
            setPingxxQrUrl('');
          }
        }}
      />
    </>
  );
}
