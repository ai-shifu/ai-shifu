'use client';

import React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import api from '@/api';
import AdminTableShell from '@/components/admin/AdminTableShell';
import {
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/components/admin/adminTableStyles';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import {
  buildBillingSwrKey,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
  resolveBillingOrderStatusLabel,
  resolveBillingOrderTypeLabel,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';
import type {
  AdminBillingOrderItem,
  AdminBillingSubscriptionItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  AdminBillingIdentityCell,
  AdminBillingSectionCard,
  resolveAdminBillingCreatorSecondary,
  resolveAdminBillingOrderFailure,
  resolveAdminBillingOrderProductName,
  resolveAdminBillingPaginationFootnote,
  resolveAdminBillingProductName,
  setAdminBillingExceptionHandledState,
  type AdminBillingCreatorTarget,
  type AdminBillingExceptionHandledMap,
} from './AdminBillingShared';

const EXCEPTION_PAGE_SIZE = 10;
const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;
const STATUS_DOT = '●';
const EMPTY_CELL_PLACEHOLDER = '-';

type AdminBillingExceptionRow = {
  rowKey: string;
  type: 'subscription' | 'order';
  orderBid?: string | null;
  creator_bid?: string | null;
  creator_mobile?: string | null;
  creator_nickname?: string | null;
  rawOrderStatus?: AdminBillingOrderItem['status'] | null;
  rawOrderType?: AdminBillingOrderItem['order_type'] | null;
  relatedOrderBid?: string | null;
  objectLabel: string;
  objectSecondary?: string | null;
  statusLabel: string;
  detailLabel: string;
  sortAt: string | null;
};

function resolveAdminBillingSubscriptionOutcome(
  t: (key: string, options?: Record<string, unknown>) => string,
  locale: string,
  item: AdminBillingSubscriptionItem,
): string {
  const currentPeriodEnd =
    formatBillingDateTime(item.current_period_end_at, locale) ||
    formatBillingDateTime(item.latest_renewal_event?.scheduled_at, locale);

  if (item.next_product_bid) {
    const product = resolveAdminBillingProductName(
      t,
      item.next_product_name_key,
      item.next_product_code || item.next_product_bid,
    );
    return currentPeriodEnd
      ? t('module.billing.admin.subscriptions.results.preorderWithDate', {
          product,
          date: currentPeriodEnd,
        })
      : t('module.billing.admin.subscriptions.results.preorder', {
          product,
        });
  }

  if (item.cancel_at_period_end) {
    return currentPeriodEnd
      ? t(
          'module.billing.admin.subscriptions.results.cancelAtPeriodEndWithDate',
          {
            date: currentPeriodEnd,
          },
        )
      : t('module.billing.admin.subscriptions.results.cancelAtPeriodEnd');
  }

  const event = item.latest_renewal_event;
  if (!event) {
    return resolveBillingEmptyLabel(t);
  }

  if (event.status === 'failed') {
    return t('module.billing.admin.subscriptions.results.renewalFailed');
  }

  if (event.event_type === 'expire') {
    return currentPeriodEnd
      ? t('module.billing.admin.subscriptions.results.expireWithDate', {
          date: currentPeriodEnd,
        })
      : t('module.billing.admin.subscriptions.results.expire');
  }

  if (event.event_type === 'retry' || event.event_type === 'renewal') {
    const scheduledAt =
      formatBillingDateTime(event.scheduled_at, locale) || currentPeriodEnd;
    return scheduledAt
      ? t(
          'module.billing.admin.subscriptions.results.renewalScheduledWithDate',
          {
            date: scheduledAt,
          },
        )
      : t('module.billing.admin.subscriptions.results.renewalScheduled');
  }

  if (event.event_type === 'cancel_effective') {
    return currentPeriodEnd
      ? t(
          'module.billing.admin.subscriptions.results.cancelAtPeriodEndWithDate',
          {
            date: currentPeriodEnd,
          },
        )
      : t('module.billing.admin.subscriptions.results.cancelAtPeriodEnd');
  }

  return resolveBillingEmptyLabel(t);
}

function parseBillingSortTime(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function resolveExceptionTypeBadgeClass(
  type: AdminBillingExceptionRow['type'],
): string {
  if (type === 'subscription') {
    return 'border-sky-200 bg-sky-50 text-sky-700';
  }
  return 'border-amber-200 bg-amber-50 text-amber-700';
}

function resolveExceptionOpsStatusClass(isHandled: boolean): string {
  if (isHandled) {
    return 'text-emerald-700 hover:bg-emerald-50';
  }
  return 'text-amber-700 hover:bg-amber-50';
}

type AdminBillingExceptionsPanelProps = {
  handledMap: AdminBillingExceptionHandledMap;
  opsStateReady: boolean;
  onAdjustCreatorBid?: (target: AdminBillingCreatorTarget) => void;
};

export function AdminBillingExceptionsPanel({
  handledMap: externalHandledMap,
  opsStateReady,
  onAdjustCreatorBid,
}: AdminBillingExceptionsPanelProps) {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  registerBillingTranslationUsage(t);
  const creatorMobileFilter = React.useMemo(() => {
    return String(searchParams.get('creator_mobile') || '').trim();
  }, [searchParams]);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [handledMap, setHandledMap] =
    React.useState<AdminBillingExceptionHandledMap>(externalHandledMap);

  React.useEffect(() => {
    setHandledMap(externalHandledMap);
  }, [externalHandledMap]);

  const { data: subscriptionCountPage } = useSWR<
    BillingPagedResponse<AdminBillingSubscriptionItem>
  >(
    buildBillingSwrKey('admin-billing-subscriptions-exception-count'),
    async () =>
      (await api.getAdminBillingSubscriptions(
        {
          page_index: 1,
          page_size: 1,
          attention_only: true,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingSubscriptionItem>,
    { revalidateOnFocus: false },
  );

  const { data: orderCountPage } = useSWR<
    BillingPagedResponse<AdminBillingOrderItem>
  >(
    buildBillingSwrKey('admin-billing-orders-exception-count'),
    async () =>
      (await api.getAdminBillingOrders(
        {
          page_index: 1,
          page_size: 1,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingOrderItem>,
    { revalidateOnFocus: false },
  );

  const subscriptionTotal = Math.max(
    Number(subscriptionCountPage?.total || 0),
    0,
  );
  const orderTotal = Math.max(Number(orderCountPage?.total || 0), 0);

  const {
    data: subscriptionsPage,
    error: subscriptionsError,
    isLoading: subscriptionsLoading,
  } = useSWR<BillingPagedResponse<AdminBillingSubscriptionItem>>(
    subscriptionCountPage
      ? buildBillingSwrKey(
          'admin-billing-subscriptions-exception-all',
          subscriptionTotal,
        )
      : null,
    async () =>
      (await api.getAdminBillingSubscriptions(
        {
          page_index: 1,
          page_size: Math.max(subscriptionTotal, 1),
          attention_only: true,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingSubscriptionItem>,
    { revalidateOnFocus: false },
  );

  const {
    data: ordersPage,
    error: ordersError,
    isLoading: ordersLoading,
  } = useSWR<BillingPagedResponse<AdminBillingOrderItem>>(
    orderCountPage
      ? buildBillingSwrKey('admin-billing-orders-exception-all', orderTotal)
      : null,
    async () =>
      (await api.getAdminBillingOrders(
        {
          page_index: 1,
          page_size: Math.max(orderTotal, 1),
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingOrderItem>,
    { revalidateOnFocus: false },
  );

  const exceptionRows = React.useMemo<AdminBillingExceptionRow[]>(() => {
    const subscriptionRows = (subscriptionsPage?.items || []).map(item => ({
      rowKey: `subscription:${item.subscription_bid}`,
      type: 'subscription' as const,
      orderBid: null,
      creator_bid: item.creator_bid,
      creator_mobile: item.creator_mobile,
      creator_nickname: item.creator_nickname,
      rawOrderStatus: null,
      rawOrderType: null,
      relatedOrderBid:
        typeof item.latest_renewal_event?.payload?.bill_order_bid === 'string'
          ? item.latest_renewal_event.payload.bill_order_bid
          : null,
      objectLabel: resolveAdminBillingProductName(
        t,
        item.product_name_key,
        item.product_code || item.product_bid,
      ),
      objectSecondary: t(
        'module.billing.admin.exceptions.targets.subscription',
      ),
      statusLabel: resolveBillingSubscriptionStatusLabel(t, item.status),
      detailLabel: resolveAdminBillingSubscriptionOutcome(
        t,
        i18n.language,
        item,
      ),
      sortAt:
        item.latest_renewal_event?.processed_at ||
        item.latest_renewal_event?.scheduled_at ||
        item.current_period_end_at,
    }));

    const orderRows = (ordersPage?.items || []).map(item => ({
      rowKey: `order:${item.bill_order_bid}`,
      type: 'order' as const,
      orderBid: item.bill_order_bid,
      creator_bid: item.creator_bid,
      creator_mobile: item.creator_mobile,
      creator_nickname: item.creator_nickname,
      rawOrderStatus: item.status,
      rawOrderType: item.order_type,
      relatedOrderBid: null,
      objectLabel: resolveAdminBillingOrderProductName(t, item),
      objectSecondary:
        item.order_type === 'subscription_renewal' ||
        item.order_type === 'subscription_start' ||
        item.order_type === 'subscription_upgrade'
          ? resolveBillingOrderTypeLabel(t, item.order_type)
          : t('module.billing.admin.exceptions.targets.order'),
      statusLabel: resolveBillingOrderStatusLabel(t, item.status),
      detailLabel: resolveAdminBillingOrderFailure(t, item),
      sortAt: item.failed_at || item.created_at,
    }));

    return [...subscriptionRows, ...orderRows].sort(
      (left, right) =>
        parseBillingSortTime(right.sortAt) - parseBillingSortTime(left.sortAt),
    );
  }, [i18n.language, ordersPage?.items, subscriptionsPage?.items, t]);

  const filteredExceptionRows = React.useMemo(() => {
    if (!creatorMobileFilter) {
      return exceptionRows;
    }
    return exceptionRows.filter(
      item => String(item.creator_mobile || '').trim() === creatorMobileFilter,
    );
  }, [creatorMobileFilter, exceptionRows]);

  const sortedExceptionRows = React.useMemo(() => {
    return [...filteredExceptionRows].sort((left, right) => {
      const leftHandled = Boolean(handledMap[left.rowKey]);
      const rightHandled = Boolean(handledMap[right.rowKey]);

      if (leftHandled !== rightHandled) {
        return leftHandled ? 1 : -1;
      }

      return (
        parseBillingSortTime(right.sortAt) - parseBillingSortTime(left.sortAt)
      );
    });
  }, [filteredExceptionRows, handledMap]);

  const total = sortedExceptionRows.length;
  const pageCount = total ? Math.ceil(total / EXCEPTION_PAGE_SIZE) : 1;
  const safePageIndex = Math.min(pageIndex, pageCount);
  const pagedRows = sortedExceptionRows.slice(
    (safePageIndex - 1) * EXCEPTION_PAGE_SIZE,
    safePageIndex * EXCEPTION_PAGE_SIZE,
  );

  React.useEffect(() => {
    if (pageIndex !== safePageIndex) {
      setPageIndex(safePageIndex);
    }
  }, [pageIndex, safePageIndex]);

  const hasAnyError = Boolean(subscriptionsError || ordersError);
  const isLoading =
    subscriptionsLoading ||
    ordersLoading ||
    !opsStateReady ||
    subscriptionCountPage === undefined ||
    orderCountPage === undefined;

  const relatedOrderMap = React.useMemo(() => {
    const entries: Array<[string, AdminBillingOrderItem]> = (
      ordersPage?.items || []
    ).map(item => [item.bill_order_bid, item]);
    return new Map<string, AdminBillingOrderItem>(entries);
  }, [ordersPage?.items]);

  const handleViewOrder = React.useCallback(
    (item: AdminBillingExceptionRow, orderBid?: string | null) => {
      const params = new URLSearchParams();
      params.set('tab', 'credits');
      if (orderBid) {
        params.set('bill_order_bid', orderBid);
        router.push(`/admin/operations/orders?${params.toString()}`);
        return;
      }
      if (item.creator_mobile) {
        params.set('creator_keyword', item.creator_mobile);
      }
      if (item.objectLabel) {
        params.set('product_keyword', item.objectLabel);
      }
      if (item.rawOrderStatus) {
        params.set('status', item.rawOrderStatus);
      }
      if (item.rawOrderType === 'topup') {
        params.set('credit_order_kind', 'topup');
      }
      if (
        item.rawOrderType === 'subscription_renewal' ||
        item.rawOrderType === 'subscription_start' ||
        item.rawOrderType === 'subscription_upgrade'
      ) {
        params.set('credit_order_kind', 'plan');
      }
      router.push(`/admin/operations/orders?${params.toString()}`);
    },
    [router],
  );

  const toggleHandled = React.useCallback(
    (rowKey: string) => {
      const isHandled = Boolean(handledMap[rowKey]);
      const next = { ...handledMap };
      if (isHandled) {
        delete next[rowKey];
      } else {
        next[rowKey] = true;
      }
      setHandledMap(next);
      void setAdminBillingExceptionHandledState(rowKey, !isHandled).catch(
        () => {
          // Request layer already shows the error; the shared state helper rolls back.
        },
      );
    },
    [handledMap],
  );

  return (
    <AdminBillingSectionCard
      title={t('module.billing.admin.exceptions.title')}
      description={t('module.billing.admin.exceptions.description')}
      error={
        hasAnyError ? t('module.billing.admin.exceptions.loadError') : null
      }
      disableContentShell
    >
      <AdminTableShell
        loading={isLoading}
        isEmpty={!pagedRows.length}
        emptyContent={t('module.billing.admin.exceptions.empty')}
        emptyColSpan={9}
        stickyActionEmpty={{
          contentColSpan: 8,
          actionClassName: getAdminStickyRightCellClass(
            'w-[96px] min-w-[96px]',
          ),
        }}
        pagination={
          pagedRows.length
            ? {
                pageIndex: safePageIndex,
                pageCount,
                onPageChange: setPageIndex,
                prevLabel: t('module.dashboard.pagination.prev'),
                nextLabel: t('module.dashboard.pagination.next'),
                prevAriaLabel: t('module.dashboard.pagination.prev'),
                nextAriaLabel: t('module.dashboard.pagination.next'),
              }
            : undefined
        }
        footnote={
          pagedRows.length
            ? resolveAdminBillingPaginationFootnote(
                t,
                safePageIndex,
                pageCount,
                total,
              )
            : null
        }
        table={emptyRow => (
          <Table className='min-w-[1320px]'>
            <TableHeader>
              <TableRow>
                <TableHead>
                  {t('module.billing.admin.subscriptions.table.creator')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.exceptions.table.type')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.exceptions.table.object')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.exceptions.table.relatedOrder')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.orders.table.status')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.exceptions.table.detail')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.exceptions.table.updatedAt')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.exceptions.table.processingStatus')}
                </TableHead>
                <TableHead
                  className={getAdminStickyRightHeaderClass(
                    'w-[96px] min-w-[96px] text-center',
                  )}
                >
                  {t('module.billing.admin.entitlements.table.actions')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {pagedRows.map(item => (
                <TableRow key={item.rowKey}>
                  {(() => {
                    const isHandled = Boolean(handledMap[item.rowKey]);
                    const relatedOrder = item.relatedOrderBid
                      ? relatedOrderMap.get(item.relatedOrderBid)
                      : null;

                    return (
                      <>
                        <TableCell className='w-[170px] min-w-[170px]'>
                          <AdminBillingIdentityCell
                            primary={item.creator_mobile}
                            secondary={resolveAdminBillingCreatorSecondary(
                              t,
                              item,
                            )}
                          />
                        </TableCell>
                        <TableCell className='w-[120px] min-w-[120px]'>
                          <Badge
                            variant='outline'
                            className={resolveExceptionTypeBadgeClass(
                              item.type,
                            )}
                          >
                            {item.type === 'subscription'
                              ? t(
                                  'module.billing.admin.exceptions.types.subscription',
                                )
                              : t(
                                  'module.billing.admin.exceptions.types.order',
                                )}
                          </Badge>
                        </TableCell>
                        <TableCell className='w-[180px] min-w-[180px] text-slate-700'>
                          <div className='space-y-1.5'>
                            <div className='font-medium text-slate-900'>
                              {item.objectLabel}
                            </div>
                            {item.objectSecondary ? (
                              <div className='text-sm text-slate-500'>
                                {item.objectSecondary}
                              </div>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell className='w-[180px] min-w-[180px] text-slate-600'>
                          {item.type === 'subscription' &&
                          item.relatedOrderBid ? (
                            <div className='space-y-1.5'>
                              <div className='text-sm font-medium text-slate-900'>
                                {relatedOrder
                                  ? resolveAdminBillingOrderProductName(
                                      t,
                                      relatedOrder,
                                    )
                                  : item.relatedOrderBid}
                              </div>
                              <Button
                                variant='ghost'
                                size='sm'
                                className='h-auto px-0 py-0 text-xs font-medium text-[#2563EB] hover:bg-transparent hover:text-[#1D4ED8]'
                                onClick={() =>
                                  handleViewOrder(
                                    {
                                      ...item,
                                      rawOrderStatus:
                                        relatedOrder?.status ||
                                        item.rawOrderStatus,
                                      rawOrderType:
                                        relatedOrder?.order_type ||
                                        item.rawOrderType,
                                      objectLabel: relatedOrder
                                        ? resolveAdminBillingOrderProductName(
                                            t,
                                            relatedOrder,
                                          )
                                        : item.objectLabel,
                                    },
                                    item.relatedOrderBid,
                                  )
                                }
                              >
                                {t(
                                  'module.billing.admin.exceptions.actions.viewOrder',
                                )}
                              </Button>
                            </div>
                          ) : (
                            <span className='text-slate-400'>
                              {resolveBillingEmptyLabel(t)}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className='w-[120px] min-w-[120px]'>
                          <Badge
                            variant='outline'
                            className='border-slate-200 bg-slate-100 text-slate-700'
                          >
                            {item.statusLabel}
                          </Badge>
                        </TableCell>
                        <TableCell className='w-[260px] min-w-[260px] text-sm text-slate-600'>
                          {item.detailLabel}
                        </TableCell>
                        <TableCell className='w-[170px] min-w-[170px] text-slate-600'>
                          {formatBillingDateTime(item.sortAt, i18n.language) ||
                            resolveBillingEmptyLabel(t)}
                        </TableCell>
                        <TableCell className='w-[120px] min-w-[120px]'>
                          <Button
                            variant='ghost'
                            size='sm'
                            aria-pressed={isHandled}
                            className='h-auto rounded-md px-0 py-0 text-left hover:bg-transparent'
                            onClick={() => toggleHandled(item.rowKey)}
                          >
                            <span
                              className={`inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium transition-colors ${resolveExceptionOpsStatusClass(isHandled)}`}
                            >
                              {isHandled ? (
                                <Check className='size-3' />
                              ) : (
                                <span
                                  aria-hidden='true'
                                  className='text-[10px] leading-none'
                                >
                                  {STATUS_DOT}
                                </span>
                              )}
                              <span>
                                {isHandled
                                  ? t(
                                      'module.billing.admin.exceptions.processingStatus.done',
                                    )
                                  : t(
                                      'module.billing.admin.exceptions.processingStatus.pending',
                                    )}
                              </span>
                            </span>
                          </Button>
                        </TableCell>
                        <TableCell
                          className={getAdminStickyRightCellClass(
                            'w-[96px] min-w-[96px] text-center',
                          )}
                        >
                          {item.type === 'subscription' &&
                          onAdjustCreatorBid ? (
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-auto px-0 py-0 text-sm font-semibold text-[#2563EB] hover:bg-transparent hover:text-[#1D4ED8]'
                              onClick={() =>
                                onAdjustCreatorBid({
                                  creator_bid: item.creator_bid,
                                  creator_mobile: item.creator_mobile,
                                  creator_nickname: item.creator_nickname,
                                  exception_row_key: item.rowKey,
                                })
                              }
                            >
                              {t('module.billing.admin.adjust.quickAction')}
                            </Button>
                          ) : item.type === 'order' ? (
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-auto px-0 py-0 text-sm font-semibold text-[#2563EB] hover:bg-transparent hover:text-[#1D4ED8]'
                              onClick={() =>
                                handleViewOrder(item, item.orderBid)
                              }
                            >
                              {t(
                                'module.billing.admin.exceptions.actions.viewOrder',
                              )}
                            </Button>
                          ) : (
                            <span className='text-slate-400'>
                              {EMPTY_CELL_PLACEHOLDER}
                            </span>
                          )}
                        </TableCell>
                      </>
                    );
                  })()}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      />
    </AdminBillingSectionCard>
  );
}
