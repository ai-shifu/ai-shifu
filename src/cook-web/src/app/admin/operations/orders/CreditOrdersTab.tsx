'use client';

import React from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import ErrorDisplay from '@/components/ErrorDisplay';
import { Button } from '@/components/ui/Button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import {
  formatBillingCredits,
  formatBillingDateTime,
  formatBillingPrice,
  resolveBillingOrderStatusLabel,
} from '@/lib/billing';
import { ErrorWithCode } from '@/lib/request';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { cn } from '@/lib/utils';
import type { BillingOrderStatus } from '@/types/billing';
import {
  resolveOperationCreditOrderKindLabel,
  resolveOperationCreditOrderPaymentChannelLabel,
  resolveOperationCreditOrderProductName,
  resolveOperationCreditOrderValidityLabel,
  resolveOperationCreditOrderProviderLabel,
} from '../operation-credit-order-helpers';
import { buildAdminOperationsUserDetailUrl } from '../operation-user-routes';
import type {
  AdminOperationCreditOrderItem,
  AdminOperationCreditOrderListResponse,
} from '../operation-credit-order-types';
import CreditOrderDetailDialog from './CreditOrderDetailDialog';
import {
  ALL_OPTION_VALUE,
  ClearableTextInput,
  EMPTY_STATE_LABEL,
  renderTooltipText,
} from './orderUiShared';

type CreditOrderFilters = {
  creator_keyword: string;
  product_keyword: string;
  credit_order_kind: string;
  status: string;
  payment_provider: string;
  start_time: string;
  end_time: string;
};

type ErrorState = { message: string; code?: number };

type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;

const PAGE_SIZE = 20;
const COLUMN_MIN_WIDTH = 90;
const COLUMN_MAX_WIDTH = 420;
const COLUMN_WIDTH_STORAGE_KEY = 'adminOperationsCreditOrdersColumnWidths';
const DEFAULT_COLUMN_WIDTHS = {
  createdAt: 180,
  creator: 220,
  orderKind: 140,
  product: 220,
  creditAmount: 130,
  paidAmount: 140,
  status: 120,
  paymentChannel: 180,
  validTo: 180,
  orderId: 220,
  action: 120,
} as const;

const createDefaultFilters = (): CreditOrderFilters => ({
  creator_keyword: '',
  product_keyword: '',
  credit_order_kind: '',
  status: 'paid',
  payment_provider: '',
  start_time: '',
  end_time: '',
});

/**
 * t('module.operationsOrder.creditOrders.emptyList')
 * t('module.operationsOrder.creditOrders.filters.creatorKeyword')
 * t('module.operationsOrder.creditOrders.filters.creatorKeywordPlaceholderEmail')
 * t('module.operationsOrder.creditOrders.filters.creatorKeywordPlaceholderPhone')
 * t('module.operationsOrder.creditOrders.filters.productKeyword')
 * t('module.operationsOrder.creditOrders.filters.productKeywordPlaceholder')
 * t('module.operationsOrder.creditOrders.filters.orderKind')
 * t('module.operationsOrder.creditOrders.filters.paymentProvider')
 * t('module.operationsOrder.creditOrders.kind.other')
 * t('module.operationsOrder.creditOrders.kind.plan')
 * t('module.operationsOrder.creditOrders.kind.topup')
 * t('module.operationsOrder.creditOrders.table.creator')
 * t('module.operationsOrder.creditOrders.table.creditAmount')
 * t('module.operationsOrder.creditOrders.table.orderId')
 * t('module.operationsOrder.creditOrders.table.orderKind')
 * t('module.operationsOrder.creditOrders.table.paymentChannel')
 * t('module.operationsOrder.creditOrders.table.product')
 * t('module.operationsOrder.creditOrders.table.validTo')
 * t('module.operationsOrder.creditOrders.creditAmountValue')
 */
export default function CreditOrdersTab() {
  const { t, i18n } = useTranslation();
  const { t: tOperationsOrder } = useTranslation('module.operationsOrder');
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const contactType = React.useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const defaultCreatorName = React.useMemo(
    () => t('module.user.defaultUserName'),
    [t],
  );
  const [expanded, setExpanded] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<ErrorState | null>(null);
  const [orders, setOrders] = React.useState<AdminOperationCreditOrderItem[]>(
    [],
  );
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(0);
  const [total, setTotal] = React.useState(0);
  const [selectedBillOrderBid, setSelectedBillOrderBid] = React.useState('');
  const [detailOpen, setDetailOpen] = React.useState(false);
  const [draftFilters, setDraftFilters] = React.useState<CreditOrderFilters>(
    () => createDefaultFilters(),
  );
  const [appliedFilters, setAppliedFilters] =
    React.useState<CreditOrderFilters>(() => createDefaultFilters());
  const requestIdRef = React.useRef(0);
  const lastRequestedPageRef = React.useRef(1);
  const { getColumnStyle, getResizeHandleProps } =
    useAdminResizableColumns<ColumnKey>({
      storageKey: COLUMN_WIDTH_STORAGE_KEY,
      defaultWidths: DEFAULT_COLUMN_WIDTHS,
      minWidth: COLUMN_MIN_WIDTH,
      maxWidth: COLUMN_MAX_WIDTH,
    });

  const locale = i18n.language || 'en-US';
  const creatorKeywordPlaceholder = React.useMemo(() => {
    if (contactType === 'email') {
      return tOperationsOrder(
        'creditOrders.filters.creatorKeywordPlaceholderEmail',
      );
    }
    return tOperationsOrder(
      'creditOrders.filters.creatorKeywordPlaceholderPhone',
    );
  }, [contactType, tOperationsOrder]);

  const fetchOrders = React.useCallback(
    async (targetPage: number, filters: CreditOrderFilters) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      lastRequestedPageRef.current = targetPage;
      setLoading(true);
      setError(null);

      try {
        const response = (await api.getAdminOperationCreditOrders({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          creator_keyword: filters.creator_keyword.trim(),
          product_keyword: filters.product_keyword.trim(),
          credit_order_kind: filters.credit_order_kind,
          status: filters.status,
          payment_provider: filters.payment_provider,
          start_time: filters.start_time,
          end_time: filters.end_time,
        })) as AdminOperationCreditOrderListResponse;

        if (requestId !== requestIdRef.current) {
          return;
        }

        setOrders(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 0);
        setTotal(response.total || 0);
      } catch (requestError) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setError({
          message: resolvedError.message || t('common.core.networkError'),
          code: resolvedError.code,
        });
        setOrders([]);
        setPageCount(0);
        setTotal(0);
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [t],
  );

  React.useEffect(() => {
    void fetchOrders(1, appliedFilters);
  }, [appliedFilters, fetchOrders]);

  const handleSearch = () => {
    const nextFilters = { ...draftFilters };
    setAppliedFilters(nextFilters);
    setPageIndex(1);
  };

  const handleReset = () => {
    const nextFilters = createDefaultFilters();
    setDraftFilters(nextFilters);
    setAppliedFilters(nextFilters);
    setPageIndex(1);
  };

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage === pageIndex) {
      return;
    }
    setPageIndex(nextPage);
    void fetchOrders(nextPage, appliedFilters);
  };

  const renderResizeHandle = (key: ColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getResizeHandleProps(key)}
    />
  );

  const statusOptions = [
    { value: ALL_OPTION_VALUE, label: t('common.core.all') },
    { value: 'pending', label: resolveBillingOrderStatusLabel(t, 'pending') },
    { value: 'paid', label: resolveBillingOrderStatusLabel(t, 'paid') },
    { value: 'failed', label: resolveBillingOrderStatusLabel(t, 'failed') },
    { value: 'refunded', label: resolveBillingOrderStatusLabel(t, 'refunded') },
    { value: 'timeout', label: resolveBillingOrderStatusLabel(t, 'timeout') },
    { value: 'canceled', label: resolveBillingOrderStatusLabel(t, 'canceled') },
    { value: 'init', label: resolveBillingOrderStatusLabel(t, 'init') },
  ];

  const orderKindOptions = [
    { value: ALL_OPTION_VALUE, label: t('common.core.all') },
    {
      value: 'plan',
      label: resolveOperationCreditOrderKindLabel(t, 'plan'),
    },
    {
      value: 'topup',
      label: resolveOperationCreditOrderKindLabel(t, 'topup'),
    },
  ];

  const paymentProviderOptions = [
    { value: ALL_OPTION_VALUE, label: t('common.core.all') },
    {
      value: 'pingxx',
      label: resolveOperationCreditOrderProviderLabel(t, 'pingxx'),
    },
    {
      value: 'stripe',
      label: resolveOperationCreditOrderProviderLabel(t, 'stripe'),
    },
    {
      value: 'manual',
      label: resolveOperationCreditOrderProviderLabel(t, 'manual'),
    },
  ];

  const primaryFilterItems = [
    {
      key: 'creator_keyword',
      label: tOperationsOrder('creditOrders.filters.creatorKeyword'),
      component: (
        <ClearableTextInput
          value={draftFilters.creator_keyword}
          placeholder={creatorKeywordPlaceholder}
          clearLabel={t('common.core.close')}
          onChange={value =>
            setDraftFilters(current => ({
              ...current,
              creator_keyword: value,
            }))
          }
        />
      ),
    },
    {
      key: 'credit_order_kind',
      label: tOperationsOrder('creditOrders.filters.orderKind'),
      component: (
        <Select
          value={draftFilters.credit_order_kind || ALL_OPTION_VALUE}
          onValueChange={value =>
            setDraftFilters(current => ({
              ...current,
              credit_order_kind: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger>
            <SelectValue
              placeholder={tOperationsOrder('creditOrders.filters.orderKind')}
            />
          </SelectTrigger>
          <SelectContent>
            {orderKindOptions.map(option => (
              <SelectItem
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'status',
      label: tOperationsOrder('filters.status'),
      component: (
        <Select
          value={draftFilters.status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setDraftFilters(current => ({
              ...current,
              status: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger>
            <SelectValue placeholder={tOperationsOrder('filters.status')} />
          </SelectTrigger>
          <SelectContent>
            {statusOptions.map(option => (
              <SelectItem
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
  ];

  const expandedFilterItems = [
    ...primaryFilterItems,
    {
      key: 'product_keyword',
      label: tOperationsOrder('creditOrders.filters.productKeyword'),
      component: (
        <ClearableTextInput
          value={draftFilters.product_keyword}
          placeholder={tOperationsOrder(
            'creditOrders.filters.productKeywordPlaceholder',
          )}
          clearLabel={t('common.core.close')}
          onChange={value =>
            setDraftFilters(current => ({
              ...current,
              product_keyword: value,
            }))
          }
        />
      ),
    },
    {
      key: 'payment_provider',
      label: tOperationsOrder('creditOrders.filters.paymentProvider'),
      component: (
        <Select
          value={draftFilters.payment_provider || ALL_OPTION_VALUE}
          onValueChange={value =>
            setDraftFilters(current => ({
              ...current,
              payment_provider: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger>
            <SelectValue
              placeholder={tOperationsOrder(
                'creditOrders.filters.paymentProvider',
              )}
            />
          </SelectTrigger>
          <SelectContent>
            {paymentProviderOptions.map(option => (
              <SelectItem
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'created_at',
      label: tOperationsOrder('filters.createdAt'),
      component: (
        <AdminDateRangeFilter
          startValue={draftFilters.start_time}
          endValue={draftFilters.end_time}
          placeholder={tOperationsOrder('filters.timeRangePlaceholder')}
          resetLabel={tOperationsOrder('filters.reset')}
          clearLabel={t('common.core.close')}
          onChange={({ start, end }) =>
            setDraftFilters(current => ({
              ...current,
              start_time: start,
              end_time: end,
            }))
          }
        />
      ),
    },
  ];

  if (error) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={() =>
            void fetchOrders(lastRequestedPageRef.current, appliedFilters)
          }
        />
      </div>
    );
  }

  return (
    <div className='h-full p-0'>
      <TooltipProvider delayDuration={150}>
        <div className='mx-auto flex h-full max-w-7xl flex-col overflow-hidden'>
          <div className='mb-5 rounded-xl border border-border bg-white p-4 shadow-sm transition-all'>
            <div className='space-y-4'>
              <div
                className={cn(
                  'grid gap-4',
                  expanded
                    ? 'grid-cols-1 xl:grid-cols-3'
                    : 'grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]',
                )}
              >
                {(expanded
                  ? expandedFilterItems.slice(0, 3)
                  : primaryFilterItems
                ).map(item => (
                  <div
                    key={item.key}
                    className='flex items-center'
                  >
                    <span
                      className={cn(
                        "mr-2 shrink-0 whitespace-nowrap text-right text-sm font-medium text-foreground after:ml-0.5 after:content-[':']",
                        'w-24',
                      )}
                    >
                      {item.label}
                    </span>
                    <div className='min-w-0 flex-1'>{item.component}</div>
                  </div>
                ))}

                {!expanded ? (
                  <div className='flex items-center justify-end gap-2'>
                    <Button
                      size='sm'
                      variant='outline'
                      onClick={handleReset}
                    >
                      {tOperationsOrder('filters.reset')}
                    </Button>
                    <Button
                      size='sm'
                      onClick={handleSearch}
                    >
                      {tOperationsOrder('filters.search')}
                    </Button>
                    <Button
                      size='sm'
                      variant='ghost'
                      className='px-2 text-primary'
                      onClick={() => setExpanded(true)}
                    >
                      {t('common.core.expand')}
                      <ChevronDown className='ml-1 h-4 w-4' />
                    </Button>
                  </div>
                ) : null}
              </div>

              {expanded ? (
                <div className='space-y-4'>
                  <div className='grid gap-4 xl:grid-cols-3'>
                    {expandedFilterItems.slice(3).map(item => (
                      <div
                        key={item.key}
                        className='flex items-center'
                      >
                        <span
                          className={cn(
                            "mr-2 shrink-0 whitespace-nowrap text-right text-sm font-medium text-foreground after:ml-0.5 after:content-[':']",
                            'w-24',
                          )}
                        >
                          {item.label}
                        </span>
                        <div className='min-w-0 flex-1'>{item.component}</div>
                      </div>
                    ))}
                  </div>

                  <div className='flex items-center justify-end gap-2'>
                    <Button
                      size='sm'
                      variant='outline'
                      onClick={handleReset}
                    >
                      {tOperationsOrder('filters.reset')}
                    </Button>
                    <Button
                      size='sm'
                      onClick={handleSearch}
                    >
                      {tOperationsOrder('filters.search')}
                    </Button>
                    <Button
                      size='sm'
                      variant='ghost'
                      className='px-2 text-primary'
                      onClick={() => setExpanded(false)}
                    >
                      {t('common.core.collapse')}
                      <ChevronUp className='ml-1 h-4 w-4' />
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div className='mb-3 text-sm text-muted-foreground'>
            {tOperationsOrder('totalCount', { count: total })}
          </div>

          <AdminTableShell
            loading={loading}
            isEmpty={orders.length === 0}
            emptyContent={tOperationsOrder('creditOrders.emptyList')}
            emptyColSpan={11}
            withTooltipProvider
            tableWrapperClassName='max-h-[calc(100vh-21rem)] overflow-auto'
            table={emptyRow => (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('createdAt')}
                    >
                      {tOperationsOrder('table.createdAt')}
                      {renderResizeHandle('createdAt')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('creator')}
                    >
                      {tOperationsOrder('creditOrders.table.creator')}
                      {renderResizeHandle('creator')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('orderKind')}
                    >
                      {tOperationsOrder('creditOrders.table.orderKind')}
                      {renderResizeHandle('orderKind')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('product')}
                    >
                      {tOperationsOrder('creditOrders.table.product')}
                      {renderResizeHandle('product')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('creditAmount')}
                    >
                      {tOperationsOrder('creditOrders.table.creditAmount')}
                      {renderResizeHandle('creditAmount')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('paidAmount')}
                    >
                      {tOperationsOrder('table.paidAmount')}
                      {renderResizeHandle('paidAmount')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('status')}
                    >
                      {tOperationsOrder('table.status')}
                      {renderResizeHandle('status')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('paymentChannel')}
                    >
                      {tOperationsOrder('creditOrders.table.paymentChannel')}
                      {renderResizeHandle('paymentChannel')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('validTo')}
                    >
                      {tOperationsOrder('creditOrders.table.validTo')}
                      {renderResizeHandle('validTo')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('orderId')}
                    >
                      {tOperationsOrder('creditOrders.table.orderId')}
                      {renderResizeHandle('orderId')}
                    </TableHead>
                    <TableHead
                      className={getAdminStickyRightHeaderClass('text-center')}
                      style={getColumnStyle('action')}
                    >
                      {tOperationsOrder('table.action')}
                      {renderResizeHandle('action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {orders.map(order => {
                    const creatorDetailUrl = buildAdminOperationsUserDetailUrl(
                      order.creator_bid,
                    );
                    const creatorContact =
                      contactType === 'email'
                        ? order.creator_email ||
                          order.creator_mobile ||
                          order.creator_identify ||
                          order.creator_bid
                        : order.creator_mobile ||
                          order.creator_email ||
                          order.creator_identify ||
                          order.creator_bid;
                    const creatorName =
                      order.creator_nickname || defaultCreatorName;
                    const kindLabel = resolveOperationCreditOrderKindLabel(
                      t,
                      order.credit_order_kind,
                    );
                    const productLabel = resolveOperationCreditOrderProductName(
                      t,
                      order,
                      EMPTY_STATE_LABEL,
                    );
                    const creditAmountLabel = tOperationsOrder(
                      'creditOrders.creditAmountValue',
                      {
                        credits: formatBillingCredits(
                          order.credit_amount,
                          locale,
                        ),
                      },
                    );
                    const paidAmountLabel = formatBillingPrice(
                      order.paid_amount,
                      order.currency,
                      locale,
                    );
                    const statusLabel = order.status
                      ? resolveBillingOrderStatusLabel(
                          t,
                          order.status as BillingOrderStatus,
                        )
                      : EMPTY_STATE_LABEL;
                    const paymentLabel =
                      resolveOperationCreditOrderPaymentChannelLabel(t, order);
                    const validityLabel =
                      resolveOperationCreditOrderValidityLabel(
                        t,
                        locale,
                        order.valid_from,
                        order.valid_to,
                        EMPTY_STATE_LABEL,
                      );

                    return (
                      <TableRow key={order.bill_order_bid}>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border text-center text-ellipsis'
                          style={getColumnStyle('createdAt')}
                        >
                          {renderTooltipText(
                            formatBillingDateTime(order.created_at, locale) ||
                              EMPTY_STATE_LABEL,
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border px-3 py-2 align-middle'
                          style={getColumnStyle('creator')}
                        >
                          <div className='space-y-1 text-center'>
                            {creatorDetailUrl ? (
                              <Link
                                href={creatorDetailUrl}
                                className='block truncate text-sm font-medium text-primary transition-colors hover:text-primary/80 hover:underline'
                              >
                                {creatorContact || EMPTY_STATE_LABEL}
                              </Link>
                            ) : (
                              <div className='truncate text-sm font-medium text-foreground'>
                                {creatorContact || EMPTY_STATE_LABEL}
                              </div>
                            )}
                            <div className='truncate text-xs text-muted-foreground'>
                              {creatorName}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('orderKind')}
                        >
                          {renderTooltipText(kindLabel)}
                        </TableCell>
                        <TableCell
                          className='border-r border-border px-3 py-2 align-middle'
                          style={getColumnStyle('product')}
                        >
                          <div className='truncate text-center text-sm font-medium text-foreground'>
                            {productLabel}
                          </div>
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('creditAmount')}
                        >
                          {renderTooltipText(creditAmountLabel)}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('paidAmount')}
                        >
                          {renderTooltipText(paidAmountLabel)}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('status')}
                        >
                          {renderTooltipText(statusLabel)}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('paymentChannel')}
                        >
                          {renderTooltipText(paymentLabel)}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('validTo')}
                        >
                          {renderTooltipText(validityLabel)}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('orderId')}
                        >
                          {renderTooltipText(order.bill_order_bid)}
                        </TableCell>
                        <TableCell
                          className={getAdminStickyRightCellClass(
                            'whitespace-nowrap px-3 py-2 text-center',
                          )}
                          style={getColumnStyle('action')}
                        >
                          <Button
                            size='sm'
                            variant='ghost'
                            className='text-primary hover:text-primary/80'
                            onClick={() => {
                              setSelectedBillOrderBid(order.bill_order_bid);
                              setDetailOpen(true);
                            }}
                          >
                            {tOperationsOrder('table.view')}
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
            footer={
              pageCount > 1 ? (
                <AdminPagination
                  pageIndex={pageIndex}
                  pageCount={pageCount}
                  onPageChange={handlePageChange}
                  prevLabel={t('module.order.paginationPrev')}
                  nextLabel={t('module.order.paginationNext')}
                  prevAriaLabel={t('module.order.paginationPrevAriaLabel')}
                  nextAriaLabel={t('module.order.paginationNextAriaLabel')}
                  className='mx-0 w-auto justify-end'
                  hideWhenSinglePage
                />
              ) : null
            }
            footerClassName='mt-3'
          />
        </div>
      </TooltipProvider>

      <CreditOrderDetailDialog
        open={detailOpen}
        billOrderBid={selectedBillOrderBid}
        onOpenChange={open => {
          setDetailOpen(open);
          if (!open) {
            setSelectedBillOrderBid('');
          }
        }}
      />
    </div>
  );
}
