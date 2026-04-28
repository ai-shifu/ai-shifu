'use client';

import React, { useCallback, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
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
import { ErrorWithCode } from '@/lib/request';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { cn } from '@/lib/utils';
import { getOperationOrderSourceLabel } from '../operation-order-source';
import { buildAdminOperationsCourseDetailUrl } from '../operation-course-routes';
import { buildAdminOperationsUserDetailUrl } from '../operation-user-routes';
import type {
  AdminOperationOrderItem,
  AdminOperationOrderListResponse,
} from '../operation-order-types';
import OperatorOrderDetailSheet from './OperatorOrderDetailSheet';
import {
  ALL_OPTION_VALUE,
  ClearableTextInput,
  EMPTY_STATE_LABEL,
  renderTooltipText,
} from './orderUiShared';

type OrderFilters = {
  user_keyword: string;
  order_bid: string;
  shifu_bid: string;
  course_name: string;
  status: string;
  order_source: string;
  payment_channel: string;
  start_time: string;
  end_time: string;
};

type ErrorState = { message: string; code?: number };

const PAGE_SIZE = 20;
const DEFAULT_ORDER_STATUS = '502';
const COLUMN_MIN_WIDTH = 90;
const COLUMN_MAX_WIDTH = 420;
const COLUMN_WIDTH_STORAGE_KEY = 'adminOperationsOrdersColumnWidths';
const DEFAULT_COLUMN_WIDTHS = {
  createdAt: 180,
  orderId: 220,
  user: 220,
  course: 200,
  status: 120,
  paidAmount: 120,
  discountAmount: 120,
  coupons: 180,
  paymentChannel: 140,
  source: 130,
  action: 120,
} as const;

type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;

const createDefaultFilters = (): OrderFilters => ({
  user_keyword: '',
  order_bid: '',
  shifu_bid: '',
  course_name: '',
  status: DEFAULT_ORDER_STATUS,
  order_source: '',
  payment_channel: '',
  start_time: '',
  end_time: '',
});

const formatMoney = (value: string | undefined, currencySymbol: string) => {
  const normalized = String(value || '').trim();
  return `${currencySymbol}${normalized || '0'}`;
};

/**
 * t('module.operationsOrder.title')
 * t('module.operationsOrder.totalCount')
 * t('module.operationsOrder.emptyList')
 * t('module.operationsOrder.filters.userKeyword')
 * t('module.operationsOrder.filters.userKeywordPlaceholder')
 * t('module.operationsOrder.filters.userKeywordPlaceholderEmail')
 * t('module.operationsOrder.filters.userKeywordPlaceholderPhone')
 * t('module.operationsOrder.filters.orderId')
 * t('module.operationsOrder.filters.orderIdPlaceholder')
 * t('module.operationsOrder.filters.courseId')
 * t('module.operationsOrder.filters.courseIdPlaceholder')
 * t('module.operationsOrder.filters.courseName')
 * t('module.operationsOrder.filters.courseNamePlaceholder')
 * t('module.operationsOrder.filters.status')
 * t('module.operationsOrder.filters.source')
 * t('module.operationsOrder.filters.paymentChannel')
 * t('module.operationsOrder.filters.createdAt')
 * t('module.operationsOrder.filters.search')
 * t('module.operationsOrder.filters.reset')
 * t('module.operationsOrder.table.createdAt')
 * t('module.operationsOrder.table.orderId')
 * t('module.operationsOrder.table.user')
 * t('module.operationsOrder.table.userId')
 * t('module.operationsOrder.table.course')
 * t('module.operationsOrder.table.source')
 * t('module.operationsOrder.table.status')
 * t('module.operationsOrder.table.paidAmount')
 * t('module.operationsOrder.table.discountAmount')
 * t('module.operationsOrder.table.paymentChannel')
 * t('module.operationsOrder.table.coupons')
 * t('module.operationsOrder.table.action')
 * t('module.operationsOrder.table.view')
 * t('module.operationsOrder.source.userPurchase')
 * t('module.operationsOrder.source.couponRedeem')
 * t('module.operationsOrder.source.importActivation')
 * t('module.operationsOrder.source.openApi')
 */
export default function LearnOrdersTab() {
  const { t, i18n } = useTranslation();
  const { t: tOperationsOrder } = useTranslation('module.operationsOrder');
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const currencySymbol = useEnvStore(
    (state: EnvStoreState) => state.currencySymbol || '',
  );
  const contactType = useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const defaultUserName = useMemo(() => t('module.user.defaultUserName'), [t]);
  const isEnglish = (i18n?.language || 'en-US').startsWith('en');
  const filterControlClassName = cn(
    'min-w-0 flex-1',
    isEnglish && 'xl:max-w-[220px]',
  );
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ErrorState | null>(null);
  const [orders, setOrders] = useState<AdminOperationOrderItem[]>([]);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [selectedOrderBid, setSelectedOrderBid] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [draftFilters, setDraftFilters] = useState<OrderFilters>(() =>
    createDefaultFilters(),
  );
  const [appliedFilters, setAppliedFilters] = useState<OrderFilters>(() =>
    createDefaultFilters(),
  );
  const requestIdRef = useRef(0);
  const lastRequestedPageRef = useRef(1);
  const { getColumnStyle, getResizeHandleProps } =
    useAdminResizableColumns<ColumnKey>({
      storageKey: COLUMN_WIDTH_STORAGE_KEY,
      defaultWidths: DEFAULT_COLUMN_WIDTHS,
      minWidth: COLUMN_MIN_WIDTH,
      maxWidth: COLUMN_MAX_WIDTH,
    });

  const userKeywordPlaceholder = useMemo(() => {
    if (contactType === 'email') {
      return tOperationsOrder('filters.userKeywordPlaceholderEmail');
    }
    return tOperationsOrder('filters.userKeywordPlaceholderPhone');
  }, [contactType, tOperationsOrder]);

  const fetchOrders = useCallback(
    async (targetPage: number, filters: OrderFilters) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      lastRequestedPageRef.current = targetPage;
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getAdminOperationOrders({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          user_keyword: filters.user_keyword.trim(),
          order_bid: filters.order_bid.trim(),
          shifu_bid: filters.shifu_bid.trim(),
          course_name: filters.course_name.trim(),
          status: filters.status,
          order_source: filters.order_source,
          payment_channel: filters.payment_channel,
          start_time: filters.start_time,
          end_time: filters.end_time,
        })) as AdminOperationOrderListResponse;
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
    { value: '501', label: t('server.order.orderStatusInit') },
    { value: '504', label: t('server.order.orderStatusToBePaid') },
    { value: '502', label: t('server.order.orderStatusSuccess') },
    { value: '503', label: t('server.order.orderStatusRefund') },
    { value: '505', label: t('server.order.orderStatusTimeout') },
  ];

  const sourceOptions = [
    { value: ALL_OPTION_VALUE, label: t('common.core.all') },
    {
      value: 'user_purchase',
      label: tOperationsOrder('source.userPurchase'),
    },
    {
      value: 'coupon_redeem',
      label: tOperationsOrder('source.couponRedeem'),
    },
    {
      value: 'import_activation',
      label: tOperationsOrder('source.importActivation'),
    },
    {
      value: 'open_api',
      label: tOperationsOrder('source.openApi'),
    },
  ];

  const paymentChannelOptions = [
    { value: ALL_OPTION_VALUE, label: t('common.core.all') },
    { value: 'pingxx', label: t('module.order.paymentChannel.pingxx') },
    { value: 'stripe', label: t('module.order.paymentChannel.stripe') },
    { value: 'manual', label: t('module.order.paymentChannel.manual') },
    { value: 'open_api', label: t('module.order.paymentChannel.open_api') },
  ];

  const resolveOrderSourceLabel = useCallback(
    (order: AdminOperationOrderItem) =>
      getOperationOrderSourceLabel(
        order,
        key => tOperationsOrder(key),
        EMPTY_STATE_LABEL,
      ),
    [tOperationsOrder],
  );

  const primaryFilterItems = [
    {
      key: 'user_keyword',
      label: tOperationsOrder('filters.userKeyword'),
      component: (
        <ClearableTextInput
          value={draftFilters.user_keyword}
          placeholder={userKeywordPlaceholder}
          clearLabel={t('common.core.close')}
          onChange={value =>
            setDraftFilters(current => ({
              ...current,
              user_keyword: value,
            }))
          }
        />
      ),
    },
    {
      key: 'shifu_bid',
      label: tOperationsOrder('filters.courseId'),
      component: (
        <ClearableTextInput
          value={draftFilters.shifu_bid}
          placeholder={tOperationsOrder('filters.courseIdPlaceholder')}
          clearLabel={t('common.core.close')}
          onChange={value =>
            setDraftFilters(current => ({
              ...current,
              shifu_bid: value,
            }))
          }
        />
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
      key: 'course_name',
      label: tOperationsOrder('filters.courseName'),
      component: (
        <ClearableTextInput
          value={draftFilters.course_name}
          placeholder={tOperationsOrder('filters.courseNamePlaceholder')}
          clearLabel={t('common.core.close')}
          onChange={value =>
            setDraftFilters(current => ({
              ...current,
              course_name: value,
            }))
          }
        />
      ),
    },
    {
      key: 'order_bid',
      label: tOperationsOrder('filters.orderId'),
      component: (
        <ClearableTextInput
          value={draftFilters.order_bid}
          placeholder={tOperationsOrder('filters.orderIdPlaceholder')}
          clearLabel={t('common.core.close')}
          onChange={value =>
            setDraftFilters(current => ({
              ...current,
              order_bid: value,
            }))
          }
        />
      ),
    },
    {
      key: 'order_source',
      label: tOperationsOrder('filters.source'),
      component: (
        <Select
          value={draftFilters.order_source || ALL_OPTION_VALUE}
          onValueChange={value =>
            setDraftFilters(current => ({
              ...current,
              order_source: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger>
            <SelectValue placeholder={tOperationsOrder('filters.source')} />
          </SelectTrigger>
          <SelectContent>
            {sourceOptions.map(option => (
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
      key: 'payment_channel',
      label: tOperationsOrder('filters.paymentChannel'),
      component: (
        <Select
          value={draftFilters.payment_channel || ALL_OPTION_VALUE}
          onValueChange={value =>
            setDraftFilters(current => ({
              ...current,
              payment_channel: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger>
            <SelectValue
              placeholder={tOperationsOrder('filters.paymentChannel')}
            />
          </SelectTrigger>
          <SelectContent>
            {paymentChannelOptions.map(option => (
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
                    <div className={filterControlClassName}>
                      {item.component}
                    </div>
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
                        <div className={filterControlClassName}>
                          {item.component}
                        </div>
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
            emptyContent={tOperationsOrder('emptyList')}
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
                      style={getColumnStyle('orderId')}
                    >
                      {tOperationsOrder('table.orderId')}
                      {renderResizeHandle('orderId')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('user')}
                    >
                      {tOperationsOrder('table.user')}
                      {renderResizeHandle('user')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('course')}
                    >
                      {tOperationsOrder('table.course')}
                      {renderResizeHandle('course')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('source')}
                    >
                      {tOperationsOrder('table.source')}
                      {renderResizeHandle('source')}
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
                      style={getColumnStyle('paidAmount')}
                    >
                      {tOperationsOrder('table.paidAmount')}
                      {renderResizeHandle('paidAmount')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('discountAmount')}
                    >
                      {tOperationsOrder('table.discountAmount')}
                      {renderResizeHandle('discountAmount')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('coupons')}
                    >
                      {tOperationsOrder('table.coupons')}
                      {renderResizeHandle('coupons')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('paymentChannel')}
                    >
                      {tOperationsOrder('table.paymentChannel')}
                      {renderResizeHandle('paymentChannel')}
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
                    const userDetailUrl = buildAdminOperationsUserDetailUrl(
                      order.user_bid,
                    );
                    const courseDetailUrl = buildAdminOperationsCourseDetailUrl(
                      order.shifu_bid,
                    );
                    const primaryContact =
                      contactType === 'email'
                        ? order.user_email ||
                          order.user_mobile ||
                          order.user_bid
                        : order.user_mobile ||
                          order.user_email ||
                          order.user_bid;
                    const nickname = order.user_nickname || defaultUserName;
                    const sourceLabel = resolveOrderSourceLabel(order);
                    const paymentLabel = order.payment_channel_key
                      ? t(order.payment_channel_key)
                      : EMPTY_STATE_LABEL;
                    const statusLabel = order.status_key
                      ? t(order.status_key)
                      : EMPTY_STATE_LABEL;
                    const couponSummary = order.coupon_codes.length
                      ? order.coupon_codes.join(', ')
                      : EMPTY_STATE_LABEL;

                    return (
                      <TableRow key={order.order_bid}>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border text-center text-ellipsis'
                          style={getColumnStyle('createdAt')}
                        >
                          {renderTooltipText(
                            formatAdminUtcDateTime(order.created_at),
                          )}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border text-center text-ellipsis'
                          style={getColumnStyle('orderId')}
                        >
                          {renderTooltipText(order.order_bid)}
                        </TableCell>
                        <TableCell
                          className='border-r border-border px-3 py-2 align-middle'
                          style={getColumnStyle('user')}
                        >
                          <div className='space-y-1 text-center'>
                            {userDetailUrl ? (
                              <Link
                                href={userDetailUrl}
                                className='block truncate text-sm font-medium text-primary transition-colors hover:text-primary/80 hover:underline'
                              >
                                {primaryContact || EMPTY_STATE_LABEL}
                              </Link>
                            ) : (
                              <div className='truncate text-sm font-medium text-foreground'>
                                {primaryContact || EMPTY_STATE_LABEL}
                              </div>
                            )}
                            <div className='truncate text-xs text-muted-foreground'>
                              {nickname}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell
                          className='border-r border-border px-3 py-2 align-middle'
                          style={getColumnStyle('course')}
                        >
                          <div className='space-y-1 text-center'>
                            {courseDetailUrl ? (
                              <Link
                                href={courseDetailUrl}
                                className='block truncate text-sm font-medium text-primary transition-colors hover:text-primary/80 hover:underline'
                              >
                                {order.shifu_name || EMPTY_STATE_LABEL}
                              </Link>
                            ) : (
                              <div className='truncate text-sm font-medium text-foreground'>
                                {order.shifu_name || EMPTY_STATE_LABEL}
                              </div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('source')}
                        >
                          {renderTooltipText(sourceLabel)}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('status')}
                        >
                          {renderTooltipText(statusLabel)}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('paidAmount')}
                        >
                          {renderTooltipText(
                            formatMoney(order.paid_price, currencySymbol),
                          )}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('discountAmount')}
                        >
                          {renderTooltipText(
                            formatMoney(order.discount_amount, currencySymbol),
                          )}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('coupons')}
                        >
                          {renderTooltipText(couponSummary)}
                        </TableCell>
                        <TableCell
                          className='overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis'
                          style={getColumnStyle('paymentChannel')}
                        >
                          {renderTooltipText(paymentLabel)}
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
                              setSelectedOrderBid(order.order_bid);
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

      <OperatorOrderDetailSheet
        open={detailOpen}
        orderBid={selectedOrderBid}
        onOpenChange={open => {
          setDetailOpen(open);
          if (!open) {
            setSelectedOrderBid('');
          }
        }}
      />
    </div>
  );
}
