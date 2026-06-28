'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import api from '@/api';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/store';
import { ErrorWithCode } from '@/lib/request';
import ErrorDisplay from '@/components/ErrorDisplay';
import OrderDetailSheet from '@/components/order/OrderDetailSheet';
import CreatorRedemptionCodesTab from './CreatorRedemptionCodesTab';
import OrdersFilterPanel from './OrdersFilterPanel';
import OrdersTable from './OrdersTable';
import {
  COLUMN_KEYS,
  COLUMN_MAX_WIDTH,
  COLUMN_MIN_WIDTH,
  COLUMN_WIDTH_STORAGE_KEY,
  DEFAULT_COLUMN_WIDTHS,
  createDefaultFilters,
  createFiltersFromSearchParams,
  PAGE_SIZE,
  QUERY_SHIFU_BID_KEY,
  QUERY_STATUS_KEY,
  QUERY_TAB_KEY,
  resolveOrdersPageTab,
  serializeShifuBidQuery,
  type ColumnKey,
  type ColumnWidthState,
  type OrderFilters,
  type OrderListResponse,
  type OrdersPageTab,
} from './ordersPageShared';
import { cn } from '@/lib/utils';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import type { OrderSummary } from '@/components/order/order-types';
import type { Shifu } from '@/types/shifu';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  ORDER_TABS_LIST_CLASSNAME,
  ORDER_TABS_TRIGGER_CLASSNAME,
} from '@/app/admin/operations/orders/orderUiShared';

const OrdersPage = () => {
  const { t, i18n } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchParamsString = searchParams?.toString() || '';
  const activeTabFromUrl = useMemo(
    () =>
      resolveOrdersPageTab(
        new URLSearchParams(searchParamsString).get(QUERY_TAB_KEY),
      ),
    [searchParamsString],
  );
  const hasStatusQuery = useMemo(
    () => new URLSearchParams(searchParamsString).has(QUERY_STATUS_KEY),
    [searchParamsString],
  );
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const currencySymbol = useEnvStore(
    (state: EnvStoreState) => state.currencySymbol,
  );
  const payOrderExpireSeconds = useEnvStore(
    (state: EnvStoreState) => state.payOrderExpireSeconds,
  );
  const initialFilters = useMemo(
    () =>
      createFiltersFromSearchParams(new URLSearchParams(searchParamsString)),
    [searchParamsString],
  );
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
  const [courses, setCourses] = useState<Shifu[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [coursesError, setCoursesError] = useState<string | null>(null);
  const [courseSearch, setCourseSearch] = useState('');
  const [filters, setFilters] = useState<OrderFilters>(() => initialFilters);
  const filtersRef = useRef<OrderFilters>(initialFilters);
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<OrdersPageTab>(activeTabFromUrl);

  const {
    setColumnWidths,
    getColumnStyle,
    getResizeHandleProps,
    isManualColumn,
    clampWidth,
  } = useAdminResizableColumns<ColumnKey>({
    storageKey: COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: DEFAULT_COLUMN_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });

  const payOrderExpireMinutes = useMemo(() => {
    if (!Number.isFinite(payOrderExpireSeconds) || payOrderExpireSeconds <= 0) {
      return 0;
    }
    return Math.ceil(payOrderExpireSeconds / 60);
  }, [payOrderExpireSeconds]);

  const formatMoney = useCallback(
    (value?: string) => {
      const normalized = value && value.trim().length > 0 ? value : '0';
      const symbol = currencySymbol || '';
      return `${symbol}${normalized}`;
    },
    [currencySymbol],
  );

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('module.order.filters.all') },
      { value: '501', label: t('server.order.orderStatusInit') },
      { value: '504', label: t('server.order.orderStatusToBePaid') },
      { value: '502', label: t('server.order.orderStatusSuccess') },
      { value: '503', label: t('server.order.orderStatusRefund') },
      {
        value: '505',
        label:
          payOrderExpireMinutes > 0
            ? t('module.order.statusLabels.timeout', {
                minutes: payOrderExpireMinutes,
              })
            : t('server.order.orderStatusTimeout'),
      },
    ],
    [payOrderExpireMinutes, t],
  );

  const channelOptions = useMemo(
    () => [
      { value: '', label: t('module.order.filters.all') },
      { value: 'pingxx', label: t('module.order.paymentChannel.pingxx') },
      { value: 'stripe', label: t('module.order.paymentChannel.stripe') },
      { value: 'alipay', label: t('module.order.paymentChannel.alipay') },
      { value: 'wechatpay', label: t('module.order.paymentChannel.wechatpay') },
      { value: 'manual', label: t('module.order.paymentChannel.manual') },
      { value: 'open_api', label: t('module.order.paymentChannel.open_api') },
    ],
    [t],
  );

  const defaultUserName = useMemo(() => t('module.user.defaultUserName'), [t]);
  const locale = i18n?.language || 'en-US';
  const filterControlClassName = cn(
    'min-w-0 flex-1',
    !locale.startsWith('zh') && 'xl:max-w-[220px]',
  );
  const filterLabelClassName = locale.startsWith('zh')
    ? 'w-16 text-right'
    : 'w-24 text-right';

  const contactType = useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const isEmailMode = contactType === 'email';

  const userBidPlaceholder = useMemo(() => {
    if (isEmailMode) {
      return t('module.order.filters.userBidEmail');
    }
    const methods = loginMethodsEnabled || [];
    const hasPhone = methods.includes('phone');
    const hasEmail = methods.includes('email');
    if (hasPhone && !hasEmail) {
      return t('module.order.filters.userBidPhone');
    }
    if (hasEmail && !hasPhone) {
      return t('module.order.filters.userBidEmail');
    }
    return t('module.order.filters.userBid');
  }, [isEmailMode, loginMethodsEnabled, t]);

  useEffect(() => {
    setActiveTab(activeTabFromUrl);
  }, [activeTabFromUrl]);

  const updateTab = useCallback(
    (nextTab: OrdersPageTab) => {
      setActiveTab(nextTab);
      const nextSearchParams = new URLSearchParams(searchParamsString);
      if (nextTab === 'orders') {
        nextSearchParams.delete(QUERY_TAB_KEY);
      } else {
        nextSearchParams.set(QUERY_TAB_KEY, nextTab);
      }
      const query = nextSearchParams.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, {
        scroll: false,
      });
    },
    [pathname, router, searchParamsString],
  );
  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  useEffect(() => {
    setFilters(prev => {
      const hasSameCourseFilters =
        prev.shifu_bids.length === initialFilters.shifu_bids.length &&
        prev.shifu_bids.every(
          (bid, index) => bid === initialFilters.shifu_bids[index],
        );
      if (
        prev.order_bid === initialFilters.order_bid &&
        prev.user_bid === initialFilters.user_bid &&
        prev.status === initialFilters.status &&
        prev.payment_channel === initialFilters.payment_channel &&
        prev.start_time === initialFilters.start_time &&
        prev.end_time === initialFilters.end_time &&
        hasSameCourseFilters
      ) {
        return prev;
      }
      return initialFilters;
    });
  }, [initialFilters]);

  const syncJumpFiltersQuery = useCallback(
    (nextFilters: Pick<OrderFilters, 'shifu_bids' | 'status'>) => {
      const nextSearchParams = new URLSearchParams(searchParamsString);
      const serializedShifuBid = serializeShifuBidQuery(nextFilters.shifu_bids);
      const normalizedStatus = nextFilters.status.trim();

      if (serializedShifuBid) {
        nextSearchParams.set(QUERY_SHIFU_BID_KEY, serializedShifuBid);
      } else {
        nextSearchParams.delete(QUERY_SHIFU_BID_KEY);
      }

      nextSearchParams.set(QUERY_STATUS_KEY, normalizedStatus);

      const query = nextSearchParams.toString();
      router.replace(query ? `/admin/orders?${query}` : '/admin/orders');
    },
    [router, searchParamsString],
  );

  const estimateWidth = (text: string, multiplier = 7) => {
    if (!text) {
      return COLUMN_MIN_WIDTH;
    }
    const approx = text.length * multiplier + 16;
    return approx;
  };

  const resolveStatusLabel = useCallback(
    (order: OrderSummary) => {
      if (order.status === 505 && payOrderExpireMinutes > 0) {
        return t('module.order.statusLabels.timeout', {
          minutes: payOrderExpireMinutes,
        });
      }
      return t(order.status_key);
    },
    [payOrderExpireMinutes, t],
  );

  const autoAdjustColumns = useCallback(
    (items: OrderSummary[]) => {
      if (!items || items.length === 0) {
        setColumnWidths(prev => {
          const next = { ...prev };
          COLUMN_KEYS.forEach(key => {
            if (!isManualColumn(key)) {
              next[key] = DEFAULT_COLUMN_WIDTHS[key];
            }
          });
          return next;
        });
        return;
      }

      const nextWidths: Partial<ColumnWidthState> = {};
      const columnValueExtractors: Record<
        ColumnKey,
        (order: OrderSummary) => string[]
      > = {
        shifu: order => [order.shifu_name || order.shifu_bid],
        user: order => [
          (isEmailMode ? order.user_email : order.user_mobile) ||
            order.user_bid,
          order.user_nickname || defaultUserName,
        ],
        status: order => [resolveStatusLabel(order)],
        paidAmount: order => [formatMoney(order.paid_price)],
        discountInfo: order => [
          order.discount_amount && order.discount_amount !== '0'
            ? formatMoney(order.discount_amount)
            : '-',
        ],
        payment: order => [t(order.payment_channel_key)],
        createdAt: order => [order.created_at],
        orderId: order => [order.order_bid],
        action: () => [t('module.order.table.view')],
      };

      items.forEach(order => {
        COLUMN_KEYS.forEach(key => {
          const texts = columnValueExtractors[key](order).filter(Boolean);
          if (texts.length === 0) {
            return;
          }
          const multiplierMap: Partial<Record<ColumnKey, number>> = {
            shifu: 4.4,
            user: 4.6,
            status: 4.4,
            paidAmount: 4.4,
            discountInfo: 4.8,
            payment: 4.4,
            createdAt: 4.8,
            orderId: 5,
            action: 4.4,
          };
          const multiplier = multiplierMap[key] ?? 7;
          const required = texts.reduce(
            (maxWidth, text) =>
              Math.max(maxWidth, estimateWidth(text, multiplier)),
            DEFAULT_COLUMN_WIDTHS[key],
          );
          if (
            !nextWidths[key] ||
            required > (nextWidths[key] ?? COLUMN_MIN_WIDTH)
          ) {
            nextWidths[key] = required;
          }
        });
      });

      setColumnWidths(prev => {
        const updated = { ...prev };
        COLUMN_KEYS.forEach(key => {
          if (isManualColumn(key)) {
            return;
          }
          const fallback = DEFAULT_COLUMN_WIDTHS[key];
          const calculated = nextWidths[key] ?? fallback;
          updated[key] = clampWidth(calculated);
        });
        return updated;
      });
    },
    [
      clampWidth,
      defaultUserName,
      formatMoney,
      isEmailMode,
      isManualColumn,
      resolveStatusLabel,
      setColumnWidths,
      t,
    ],
  );

  useEffect(() => {
    if (!isInitialized || isGuest) {
      setCourses([]);
      setCoursesLoading(false);
      setCoursesError(null);
      return;
    }

    let canceled = false;
    const loadCourses = async () => {
      setCoursesLoading(true);
      setCoursesError(null);
      try {
        const pageSize = 100;
        let pageIndex = 1;
        const collected: Shifu[] = [];
        const seen = new Set<string>();

        while (true) {
          const { items } = await api.getAdminOrderShifus({
            page_index: pageIndex,
            page_size: pageSize,
          });
          const pageItems = (items || []) as Shifu[];
          pageItems.forEach(item => {
            if (item?.bid && !seen.has(item.bid)) {
              seen.add(item.bid);
              collected.push(item);
            }
          });
          if (pageItems.length < pageSize) {
            break;
          }
          pageIndex += 1;
        }

        if (!canceled) {
          setCourses(collected);
        }
      } catch {
        if (!canceled) {
          setCourses([]);
          setCoursesError(t('common.core.networkError'));
        }
      } finally {
        if (!canceled) {
          setCoursesLoading(false);
        }
      }
    };

    loadCourses();

    return () => {
      canceled = true;
    };
  }, [isInitialized, isGuest, t]);

  const fetchOrders = useCallback(
    async (targetPage: number, nextFilters?: OrderFilters) => {
      const resolvedFilters = nextFilters ?? filtersRef.current;
      const shifuBidValue = resolvedFilters.shifu_bids
        .map(bid => bid.trim())
        .filter(Boolean)
        .join(',');
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getAdminOrders({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          order_bid: resolvedFilters.order_bid.trim(),
          user_bid: resolvedFilters.user_bid.trim(),
          shifu_bid: shifuBidValue,
          status: resolvedFilters.status,
          payment_channel: resolvedFilters.payment_channel,
          start_time: resolvedFilters.start_time,
          end_time: resolvedFilters.end_time,
        })) as OrderListResponse;

        const list = response.items || [];
        setOrders(list);
        autoAdjustColumns(list);
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
    [autoAdjustColumns, t],
  );

  useEffect(() => {
    if (isInitialized && !isGuest && activeTab === 'orders') {
      fetchOrders(1);
    }
  }, [activeTab, fetchOrders, i18n.language, isGuest, isInitialized]);

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
    if (!isInitialized || isGuest || hasStatusQuery || activeTab !== 'orders') {
      return;
    }
    syncJumpFiltersQuery(initialFilters);
  }, [
    activeTab,
    hasStatusQuery,
    initialFilters,
    isGuest,
    isInitialized,
    syncJumpFiltersQuery,
  ]);
  const handleFilterChange = (
    key: Exclude<keyof OrderFilters, 'shifu_bids'>,
    value: string,
  ) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const handleCourseToggle = (courseBid: string) => {
    setFilters(prev => {
      const exists = prev.shifu_bids.includes(courseBid);
      const nextBids = exists
        ? prev.shifu_bids.filter(bid => bid !== courseBid)
        : [...prev.shifu_bids, courseBid];
      return { ...prev, shifu_bids: nextBids };
    });
  };

  const handleSearch = () => {
    syncJumpFiltersQuery(filters);
    fetchOrders(1, filters);
  };

  const handleReset = () => {
    const cleared = createDefaultFilters();
    setFilters(cleared);
    setCourseSearch('');
    syncJumpFiltersQuery(cleared);
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

  if (activeTab === 'orders' && error) {
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
      <div className='mx-auto flex h-full max-w-7xl flex-col overflow-hidden'>
        <AdminBreadcrumb items={[{ label: t('module.order.title') }]} />
        <Tabs
          value={activeTab}
          className='flex min-h-0 flex-1 flex-col'
          onValueChange={value => updateTab(value as OrdersPageTab)}
        >
          <AdminTitle
            title={t('module.order.title')}
            tabs={
              <TabsList
                className={ORDER_TABS_LIST_CLASSNAME}
                data-testid='creator-orders-tabs'
              >
                <TabsTrigger
                  value='orders'
                  className={ORDER_TABS_TRIGGER_CLASSNAME}
                >
                  {t('module.order.tabs.orders')}
                </TabsTrigger>
                <TabsTrigger
                  value='redemptionCodes'
                  className={ORDER_TABS_TRIGGER_CLASSNAME}
                >
                  {t('module.order.tabs.redemptionCodes')}
                </TabsTrigger>
              </TabsList>
            }
          />

          <div className='min-h-0 flex-1 overflow-hidden pr-1'>
            {activeTab === 'orders' ? (
              <div className='flex h-full min-h-0 flex-col gap-5 pb-6'>
                <OrdersFilterPanel
                  filters={filters}
                  courses={courses}
                  coursesLoading={coursesLoading}
                  coursesError={coursesError}
                  courseSearch={courseSearch}
                  expanded={expanded}
                  userBidPlaceholder={userBidPlaceholder}
                  statusOptions={statusOptions}
                  channelOptions={channelOptions}
                  contentClassName={filterControlClassName}
                  expandedLabelClassName={filterLabelClassName}
                  onCourseSearchChange={setCourseSearch}
                  onExpandedChange={setExpanded}
                  onFilterChange={handleFilterChange}
                  onCourseToggle={handleCourseToggle}
                  onReset={handleReset}
                  onSearch={handleSearch}
                />

                <OrdersTable
                  orders={orders}
                  loading={loading}
                  total={total}
                  pageIndex={pageIndex}
                  pageCount={pageCount}
                  isEmailMode={isEmailMode}
                  defaultUserName={defaultUserName}
                  getColumnStyle={getColumnStyle}
                  getResizeHandleProps={getResizeHandleProps}
                  formatMoney={formatMoney}
                  resolveStatusLabel={resolveStatusLabel}
                  onPageChange={handlePageChange}
                  onViewDetail={handleViewDetail}
                />
              </div>
            ) : (
              <CreatorRedemptionCodesTab reloadKey={0} />
            )}
          </div>
        </Tabs>
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
    </div>
  );
};

export default OrdersPage;
