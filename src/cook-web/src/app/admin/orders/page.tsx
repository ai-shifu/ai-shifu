'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import api from '@/api';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/store';
import { ErrorWithCode } from '@/lib/request';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
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
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import OrderDetailSheet from '@/components/order/OrderDetailSheet';
import type { OrderSummary } from '@/components/order/order-types';

type OrderListResponse = {
  items: OrderSummary[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

const PAGE_SIZE = 20;

const OrdersPage = () => {
  const { t, i18n } = useTranslation();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; code?: number } | null>(
    null,
  );
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [total, setTotal] = useState(0);
  const [selectedOrder, setSelectedOrder] = useState<OrderSummary | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [filters, setFilters] = useState({
    order_bid: '',
    user_bid: '',
    shifu_bid: '',
    status: '',
    payment_channel: '',
  });
  const filtersRef = useRef(filters);

  const ALL_OPTION_VALUE = '__all__';

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('module.order.filters.all') },
      { value: '501', label: t('server.order.orderStatusInit') },
      { value: '504', label: t('server.order.orderStatusToBePaid') },
      { value: '502', label: t('server.order.orderStatusSuccess') },
      { value: '503', label: t('server.order.orderStatusRefund') },
      { value: '505', label: t('server.order.orderStatusTimeout') },
    ],
    [t],
  );

  const channelOptions = useMemo(
    () => [
      { value: '', label: t('module.order.filters.all') },
      { value: 'pingxx', label: t('module.order.paymentChannel.pingxx') },
      { value: 'stripe', label: t('module.order.paymentChannel.stripe') },
    ],
    [t],
  );

  const displayStatusValue = filters.status || ALL_OPTION_VALUE;
  const displayChannelValue = filters.payment_channel || ALL_OPTION_VALUE;

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  const fetchOrders = useCallback(
    async (targetPage: number, nextFilters?: typeof filters) => {
      const resolvedFilters = nextFilters ?? filtersRef.current;
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getAdminOrders({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          order_bid: resolvedFilters.order_bid.trim(),
          user_bid: resolvedFilters.user_bid.trim(),
          shifu_bid: resolvedFilters.shifu_bid.trim(),
          status: resolvedFilters.status,
          payment_channel: resolvedFilters.payment_channel,
        })) as OrderListResponse;

        setOrders(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 1);
        setTotal(response.total || 0);
      } catch (err) {
        if (err instanceof ErrorWithCode) {
          setError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setError({ message: err.message });
        } else {
          setError({ message: t('common.core.unknownError') });
        }
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (isInitialized && !isGuest) {
      fetchOrders(1);
    }
  }, [fetchOrders, isInitialized, isGuest]);

  useEffect(() => {
    if (!isInitialized) return;
    if (isGuest) {
      const currentPath = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?redirect=${currentPath}`;
    }
  }, [isInitialized, isGuest]);

  useEffect(() => {
    if (isInitialized && !isGuest) {
      fetchOrders(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i18n.language]);

  const handleFilterChange = (key: string, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const handleSearch = () => {
    fetchOrders(1, filters);
  };

  const handleReset = () => {
    const cleared = {
      order_bid: '',
      user_bid: '',
      shifu_bid: '',
      status: '',
      payment_channel: '',
    };
    setFilters(cleared);
    fetchOrders(1, cleared);
  };

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > pageCount || nextPage === pageIndex) {
      return;
    }
    fetchOrders(nextPage);
  };

  const handleViewDetail = (order: OrderSummary) => {
    setSelectedOrder(order);
    setDetailOpen(true);
  };

  const resolveStatusVariant = (status: number) => {
    if (status === 502) {
      return 'default';
    }
    if (status === 503 || status === 505) {
      return 'destructive';
    }
    return 'secondary';
  };

  if (error) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={() => fetchOrders(pageIndex)}
        />
      </div>
    );
  }

  return (
    <div className='h-full p-0'>
      <div className='max-w-7xl mx-auto h-full overflow-hidden flex flex-col'>
        <div className='flex items-center justify-between mb-5'>
          <h1 className='text-2xl font-semibold text-gray-900'>
            {t('module.order.title')}
          </h1>
          <div className='text-sm text-muted-foreground'>
            {t('module.order.totalCount', { count: total })}
          </div>
        </div>

        <div className='rounded-xl border border-border bg-white p-4 mb-5 shadow-sm'>
          <div className='grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5'>
            <Input
              value={filters.order_bid}
              onChange={event =>
                handleFilterChange('order_bid', event.target.value)
              }
              placeholder={t('module.order.filters.orderBid')}
              className='h-9'
            />
            <Input
              value={filters.user_bid}
              onChange={event =>
                handleFilterChange('user_bid', event.target.value)
              }
              placeholder={t('module.order.filters.userBid')}
              className='h-9'
            />
            <Input
              value={filters.shifu_bid}
              onChange={event =>
                handleFilterChange('shifu_bid', event.target.value)
              }
              placeholder={t('module.order.filters.shifuBid')}
              className='h-9'
            />
            <Select
              value={displayStatusValue}
              onValueChange={value =>
                handleFilterChange(
                  'status',
                  value === ALL_OPTION_VALUE ? '' : value,
                )
              }
            >
              <SelectTrigger className='h-9'>
                <SelectValue placeholder={t('module.order.filters.status')} />
              </SelectTrigger>
              <SelectContent>
                {statusOptions.map(option => (
                  <SelectItem
                    key={option.value || 'all'}
                    value={option.value || ALL_OPTION_VALUE}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={displayChannelValue}
              onValueChange={value =>
                handleFilterChange(
                  'payment_channel',
                  value === ALL_OPTION_VALUE ? '' : value,
                )
              }
            >
              <SelectTrigger className='h-9'>
                <SelectValue placeholder={t('module.order.filters.channel')} />
              </SelectTrigger>
              <SelectContent>
                {channelOptions.map(option => (
                  <SelectItem
                    key={option.value || 'all'}
                    value={option.value || ALL_OPTION_VALUE}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='mt-4 flex gap-2'>
            <Button
              size='sm'
              onClick={handleSearch}
            >
              {t('module.order.filters.search')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              onClick={handleReset}
            >
              {t('module.order.filters.reset')}
            </Button>
          </div>
        </div>

        <div className='flex-1 overflow-auto'>
          {loading ? (
            <div className='flex items-center justify-center h-40'>
              <Loading />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('module.order.table.orderId')}</TableHead>
                  <TableHead>{t('module.order.table.shifu')}</TableHead>
                  <TableHead>{t('module.order.table.user')}</TableHead>
                  <TableHead>{t('module.order.table.amount')}</TableHead>
                  <TableHead>{t('module.order.table.status')}</TableHead>
                  <TableHead>{t('module.order.table.payment')}</TableHead>
                  <TableHead>{t('module.order.table.createdAt')}</TableHead>
                  <TableHead className='text-right'>
                    {t('module.order.table.action')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.length === 0 && (
                  <TableEmpty colSpan={8}>
                    {t('module.order.emptyList')}
                  </TableEmpty>
                )}
                {orders.map(order => (
                  <TableRow key={order.order_bid}>
                    <TableCell className='font-mono text-xs'>
                      {order.order_bid}
                    </TableCell>
                    <TableCell>
                      <div className='font-medium text-foreground'>
                        {order.shifu_name || order.shifu_bid}
                      </div>
                      <div className='text-xs text-muted-foreground'>
                        {order.shifu_bid}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className='font-medium text-foreground'>
                        {order.user_mobile || order.user_bid}
                      </div>
                      <div className='text-xs text-muted-foreground'>
                        {order.user_nickname || order.user_bid}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className='font-semibold text-foreground'>
                        {order.paid_price}
                      </div>
                      <div className='text-xs text-muted-foreground'>
                        {t('module.order.table.payable')}: {order.payable_price}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={resolveStatusVariant(order.status)}>
                        {t(order.status_key)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className='text-sm text-foreground'>
                        {t(order.payment_channel_key)}
                      </div>
                    </TableCell>
                    <TableCell className='text-xs text-muted-foreground'>
                      {order.created_at}
                    </TableCell>
                    <TableCell className='text-right'>
                      <Button
                        size='sm'
                        variant='outline'
                        onClick={() => handleViewDetail(order)}
                      >
                        {t('module.order.table.view')}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        <div className='mt-4 flex items-center justify-between'>
          <div className='text-xs text-muted-foreground'>
            {t('module.order.pagination', {
              page: pageIndex,
              total: pageCount,
            })}
          </div>
          <div className='flex items-center gap-2'>
            <Button
              size='sm'
              variant='outline'
              disabled={pageIndex <= 1}
              onClick={() => handlePageChange(pageIndex - 1)}
            >
              {t('module.order.paginationPrev')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              disabled={pageIndex >= pageCount}
              onClick={() => handlePageChange(pageIndex + 1)}
            >
              {t('module.order.paginationNext')}
            </Button>
          </div>
        </div>
      </div>

      <OrderDetailSheet
        open={detailOpen}
        orderBid={selectedOrder?.order_bid}
        onOpenChange={open => {
          setDetailOpen(open);
          if (!open) {
            setSelectedOrder(null);
          }
        }}
      />
    </div>
  );
};

export default OrdersPage;
