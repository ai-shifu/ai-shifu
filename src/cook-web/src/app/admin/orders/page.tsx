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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { ScrollArea } from '@/components/ui/ScrollArea';
import { Calendar } from '@/components/ui/Calendar';
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
import ImportActivationDialog from '@/components/order/ImportActivationDialog';
import { cn } from '@/lib/utils';
import { CalendarIcon, Check, ChevronDown, ChevronUp } from 'lucide-react';
import type { OrderSummary } from '@/components/order/order-types';
import type { Shifu } from '@/types/shifu';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';

type OrderListResponse = {
  items: OrderSummary[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

type OrderFilters = {
  order_bid: string;
  user_bid: string;
  shifu_bids: string[];
  status: string;
  payment_channel: string;
  start_time: string;
  end_time: string;
};

const PAGE_SIZE = 20;
const COLUMN_MIN_WIDTH = 80;
const COLUMN_MAX_WIDTH = 360;
const COLUMN_WIDTH_STORAGE_KEY = 'adminOrdersColumnWidths';

const DEFAULT_COLUMN_WIDTHS = {
  orderId: 260,
  shifu: 120,
  user: 160,
  amount: 70,
  status: 110,
  payment: 90,
  createdAt: 170,
  action: 100,
};

type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;
type ColumnWidthState = Record<ColumnKey, number>;
const COLUMN_KEYS = Object.keys(DEFAULT_COLUMN_WIDTHS) as ColumnKey[];

const clampWidth = (value: number): number =>
  Math.min(COLUMN_MAX_WIDTH, Math.max(COLUMN_MIN_WIDTH, value));

const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';

const createColumnWidthState = (
  overrides?: Partial<ColumnWidthState>,
): ColumnWidthState => {
  const widths = { ...DEFAULT_COLUMN_WIDTHS };
  COLUMN_KEYS.forEach(key => {
    const nextValue = overrides?.[key];
    if (typeof nextValue === 'number' && Number.isFinite(nextValue)) {
      widths[key] = clampWidth(nextValue);
    } else {
      widths[key] = clampWidth(widths[key]);
    }
  });
  return widths;
};

const loadStoredColumnWidths = (): ColumnWidthState => {
  if (typeof window === 'undefined') {
    return createColumnWidthState();
  }
  try {
    const serialized = window.localStorage.getItem(COLUMN_WIDTH_STORAGE_KEY);
    if (!serialized) {
      return createColumnWidthState();
    }
    const parsed = JSON.parse(serialized) as Partial<ColumnWidthState>;
    return createColumnWidthState(parsed);
  } catch (error) {
    console.warn('Failed to load stored column widths', error);
    return createColumnWidthState();
  }
};

const formatDateValue = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const parseDateValue = (value: string) => {
  if (!value) {
    return undefined;
  }
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }
  return parsed;
};

type DateRangeFilterProps = {
  startValue: string;
  endValue: string;
  placeholder: string;
  resetLabel: string;
  onChange: (range: { start: string; end: string }) => void;
};

const DateRangeFilter = ({
  startValue,
  endValue,
  placeholder,
  resetLabel,
  onChange,
}: DateRangeFilterProps) => {
  const selectedRange = React.useMemo(
    () => ({
      from: parseDateValue(startValue),
      to: parseDateValue(endValue),
    }),
    [startValue, endValue],
  );
  const label = React.useMemo(() => {
    if (selectedRange.from && selectedRange.to) {
      return `${formatDateValue(selectedRange.from)} ~ ${formatDateValue(
        selectedRange.to,
      )}`;
    }
    if (selectedRange.from) {
      return formatDateValue(selectedRange.from);
    }
    return placeholder;
  }, [placeholder, selectedRange]);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          size='sm'
          variant='outline'
          type='button'
          className='h-9 w-full justify-between font-normal'
        >
          <span
            className={cn(
              'flex-1 truncate text-left',
              startValue ? 'text-foreground' : 'text-muted-foreground',
            )}
          >
            {label}
          </span>
          <CalendarIcon className='h-4 w-4 text-muted-foreground' />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align='start'
        className='w-auto max-w-[90vw] p-0'
      >
        <Calendar
          mode='range'
          numberOfMonths={2}
          selected={selectedRange}
          onSelect={range =>
            onChange({
              start: range?.from ? formatDateValue(range.from) : '',
              end: range?.to ? formatDateValue(range.to) : '',
            })
          }
          className='p-3 md:p-4 [--cell-size:2.4rem]'
        />
        <div className='flex items-center justify-end gap-2 border-t border-border px-3 py-2'>
          <Button
            size='sm'
            variant='ghost'
            type='button'
            onClick={() => onChange({ start: '', end: '' })}
          >
            {resetLabel}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
};

const OrdersPage = () => {
  const { t, i18n } = useTranslation();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
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
  const [importOpen, setImportOpen] = useState(false);
  const [courses, setCourses] = useState<Shifu[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [coursesError, setCoursesError] = useState<string | null>(null);
  const [courseSearch, setCourseSearch] = useState('');
  const [filters, setFilters] = useState<OrderFilters>({
    order_bid: '',
    user_bid: '',
    shifu_bids: [],
    status: '',
    payment_channel: '',
    start_time: '',
    end_time: '',
  });
  const filtersRef = useRef<OrderFilters>(filters);
  const [expanded, setExpanded] = useState(false);
  const [cols, setCols] = useState(4);

  useEffect(() => {
    const handleResize = () => {
      if (typeof window === 'undefined') return;
      const width = window.innerWidth;
      if (width >= 1024) setCols(3);
      else if (width >= 768) setCols(2);
      else setCols(1);
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const [columnWidths, setColumnWidths] = useState<ColumnWidthState>(() =>
    loadStoredColumnWidths(),
  );
  const columnResizeRef = useRef<{
    key: ColumnKey;
    startX: number;
    startWidth: number;
  } | null>(null);
  const manualResizeRef = useRef<Record<ColumnKey, boolean>>(
    COLUMN_KEYS.reduce(
      (acc, key) => ({ ...acc, [key]: false }),
      {} as Record<ColumnKey, boolean>,
    ),
  );
  const initializedManualRef = useRef(false);

  useEffect(() => {
    if (initializedManualRef.current) {
      return;
    }
    initializedManualRef.current = true;
    COLUMN_KEYS.forEach(key => {
      const storedWidth = columnWidths[key];
      const defaultWidth = DEFAULT_COLUMN_WIDTHS[key];
      if (Math.abs(storedWidth - defaultWidth) > 0.5) {
        manualResizeRef.current[key] = true;
      }
    });
  }, [columnWidths]);

  useEffect(() => {
    const hasManualResize = Object.values(manualResizeRef.current).some(
      Boolean,
    );
    if (!hasManualResize || typeof window === 'undefined') {
      return;
    }
    try {
      window.localStorage.setItem(
        COLUMN_WIDTH_STORAGE_KEY,
        JSON.stringify(columnWidths),
      );
    } catch (error) {
      console.warn('Failed to persist column widths', error);
    }
  }, [columnWidths]);

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
      { value: 'manual', label: t('module.order.paymentChannel.manual') },
    ],
    [t],
  );

  const userBidPlaceholder = useMemo(() => {
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
  }, [loginMethodsEnabled, t]);

  const displayStatusValue = filters.status || ALL_OPTION_VALUE;
  const displayChannelValue = filters.payment_channel || ALL_OPTION_VALUE;

  const courseNameMap = useMemo(() => {
    const map = new Map<string, string>();
    courses.forEach(course => {
      if (!course.bid) {
        return;
      }
      map.set(course.bid, course.name || course.bid);
    });
    return map;
  }, [courses]);

  const selectedCourseNames = useMemo(
    () => filters.shifu_bids.map(bid => courseNameMap.get(bid) || bid),
    [courseNameMap, filters.shifu_bids],
  );

  const selectedCourseLabel = useMemo(() => {
    if (selectedCourseNames.length === 0) {
      return t('module.order.filters.shifuBid');
    }
    if (selectedCourseNames.length <= 2) {
      return selectedCourseNames.join(', ');
    }
    const shortList = selectedCourseNames.slice(0, 2).join(', ');
    return `${shortList} +${selectedCourseNames.length - 2}`;
  }, [selectedCourseNames, t]);

  const filteredCourses = useMemo(() => {
    const keyword = courseSearch.trim().toLowerCase();
    if (!keyword) {
      return courses;
    }
    return courses.filter(course => {
      const name = (course.name || '').toLowerCase();
      const bid = (course.bid || '').toLowerCase();
      const matchesName = name.includes(keyword);
      const matchesBid = Boolean(bid && bid === keyword);
      return matchesName || matchesBid;
    });
  }, [courseSearch, courses]);

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  const startColumnResize = useCallback(
    (key: ColumnKey, clientX: number) => {
      columnResizeRef.current = {
        key,
        startX: clientX,
        startWidth: columnWidths[key],
      };
      manualResizeRef.current[key] = true;
    },
    [columnWidths],
  );

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const info = columnResizeRef.current;
      if (!info) {
        return;
      }
      const delta = event.clientX - info.startX;
      const desiredWidth = info.startWidth + delta;
      const nextWidth = Math.min(
        COLUMN_MAX_WIDTH,
        Math.max(COLUMN_MIN_WIDTH, desiredWidth),
      );
      setColumnWidths(prev => {
        if (Math.abs(prev[info.key] - nextWidth) < 0.5) {
          return prev;
        }
        return { ...prev, [info.key]: nextWidth };
      });
    };

    const handleMouseUp = () => {
      columnResizeRef.current = null;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  const getColumnStyle = useCallback(
    (key: ColumnKey) => {
      const width = columnWidths[key];
      return {
        width,
        minWidth: width,
        maxWidth: width,
      };
    },
    [columnWidths],
  );

  const estimateWidth = (text: string, multiplier = 7) => {
    if (!text) {
      return COLUMN_MIN_WIDTH;
    }
    const approx = text.length * multiplier + 16;
    return approx;
  };

  const autoAdjustColumns = useCallback(
    (items: OrderSummary[]) => {
      if (!items || items.length === 0) {
        setColumnWidths(prev => {
          const next = { ...prev };
          COLUMN_KEYS.forEach(key => {
            if (!manualResizeRef.current[key]) {
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
        orderId: order => [order.order_bid],
        shifu: order => [order.shifu_name || order.shifu_bid],
        user: order => [
          order.user_mobile || order.user_bid,
          order.user_nickname || order.user_bid,
        ],
        amount: order => [String(order.payable_price)],
        status: order => [t(order.status_key)],
        payment: order => [t(order.payment_channel_key)],
        createdAt: order => [order.created_at],
        action: () => [t('module.order.table.view')],
      };

      items.forEach(order => {
        COLUMN_KEYS.forEach(key => {
          const texts = columnValueExtractors[key](order).filter(Boolean);
          if (texts.length === 0) {
            return;
          }
          const multiplierMap: Partial<Record<ColumnKey, number>> = {
            orderId: 5,
            shifu: 4.4,
            user: 4.6,
            amount: 4,
            status: 4.4,
            payment: 4.4,
            createdAt: 4.8,
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
          if (manualResizeRef.current[key]) {
            return;
          }
          const fallback = DEFAULT_COLUMN_WIDTHS[key];
          const calculated = nextWidths[key] ?? fallback;
          updated[key] = Math.min(
            COLUMN_MAX_WIDTH,
            Math.max(COLUMN_MIN_WIDTH, calculated),
          );
        });
        return updated;
      });
    },
    [t],
  );

  const renderResizeHandle = (key: ColumnKey) => (
    <span
      className='absolute top-0 right-0 h-full w-2 cursor-col-resize select-none'
      onMouseDown={event => {
        event.preventDefault();
        startColumnResize(key, event.clientX);
      }}
      aria-hidden='true'
    />
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
          const { items } = await api.getShifuList({
            page_index: pageIndex,
            page_size: pageSize,
            is_favorite: false,
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
      } catch (error) {
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
    fetchOrders(1, filters);
  };

  const handleReset = () => {
    const cleared: OrderFilters = {
      order_bid: '',
      user_bid: '',
      shifu_bids: [],
      status: '',
      payment_channel: '',
      start_time: '',
      end_time: '',
    };
    setFilters(cleared);
    setCourseSearch('');
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

  const filterItems = [
    {
      key: 'order_bid',
      label: t('module.order.filters.orderBid'),
      component: (
        <Input
          value={filters.order_bid}
          onChange={event =>
            handleFilterChange('order_bid', event.target.value)
          }
          placeholder={t('module.order.filters.orderBid')}
          className='h-9'
        />
      ),
    },
    {
      key: 'user_bid',
      label: userBidPlaceholder,
      component: (
        <Input
          value={filters.user_bid}
          onChange={event =>
            handleFilterChange('user_bid', event.target.value)
          }
          placeholder={userBidPlaceholder}
          className='h-9'
        />
      ),
    },
    {
      key: 'shifu_bids',
      label: t('module.order.filters.shifuBid'),
      component: (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              size='sm'
              variant='outline'
              type='button'
              className='h-9 w-full justify-between font-normal'
              title={selectedCourseNames.join(', ')}
            >
              <span
                className={cn(
                  'flex-1 truncate text-left',
                  filters.shifu_bids.length === 0
                    ? 'text-muted-foreground'
                    : 'text-foreground',
                )}
              >
                {selectedCourseLabel}
              </span>
              <ChevronDown className='h-4 w-4 text-muted-foreground' />
            </Button>
          </PopoverTrigger>
          <PopoverContent
            align='start'
            className='p-3'
            style={{
              width: 'var(--radix-popover-trigger-width)',
              maxWidth: 'var(--radix-popover-trigger-width)',
            }}
          >
            <Input
              value={courseSearch}
              onChange={event => setCourseSearch(event.target.value)}
              placeholder={t('module.order.filters.searchCourseOrId')}
              className='h-8'
            />
            <ScrollArea className='mt-3 h-48'>
              {coursesLoading ? (
                <div className='flex items-center justify-center py-4'>
                  <Loading className='h-5 w-5' />
                </div>
              ) : coursesError ? (
                <div className='px-2 py-3 text-xs text-destructive'>
                  {coursesError}
                </div>
              ) : filteredCourses.length === 0 ? (
                <div className='px-2 py-3 text-xs text-muted-foreground'>
                  {t('common.core.noShifus')}
                </div>
              ) : (
                <div className='space-y-1'>
                  {filteredCourses.map(course => {
                    const isSelected = filters.shifu_bids.includes(
                      course.bid,
                    );
                    const courseName = course.name || course.bid;
                    return (
                      <button
                        key={course.bid}
                        type='button'
                        onClick={() => handleCourseToggle(course.bid)}
                        className='flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent'
                        aria-pressed={isSelected}
                      >
                        <span
                          className={cn(
                            'mt-0.5 flex h-4 w-4 items-center justify-center rounded border',
                            isSelected
                              ? 'border-primary bg-primary text-primary-foreground'
                              : 'border-muted-foreground/40 text-transparent',
                          )}
                        >
                          <Check className='h-3 w-3' />
                        </span>
                        <span className='flex flex-col min-w-0'>
                          <span className='text-sm text-foreground truncate'>
                            {courseName}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </ScrollArea>
          </PopoverContent>
        </Popover>
      ),
    },
    {
      key: 'status',
      label: t('module.order.filters.status'),
      component: (
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
                className={SINGLE_SELECT_ITEM_CLASS}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'date_range',
      label: t('module.order.table.createdAt'),
      component: (
        <DateRangeFilter
          startValue={filters.start_time}
          endValue={filters.end_time}
          onChange={range => {
            handleFilterChange('start_time', range.start);
            handleFilterChange('end_time', range.end);
          }}
          placeholder={`${t('module.order.filters.startTime')} ~ ${t(
            'module.order.filters.endTime',
          )}`}
          resetLabel={t('module.order.filters.reset')}
        />
      ),
    },
    {
      key: 'payment_channel',
      label: t('module.order.filters.channel'),
      component: (
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
                className={SINGLE_SELECT_ITEM_CLASS}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
  ];

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
          <div className='flex items-center gap-3'>
            <div className='text-sm text-muted-foreground'>
              {t('module.order.totalCount', { count: total })}
            </div>
            <Button
              size='sm'
              onClick={() => setImportOpen(true)}
            >
              {t('module.order.importActivation.action')}
            </Button>
          </div>
        </div>

        <div className='rounded-xl border border-border bg-white p-4 mb-5 shadow-sm transition-all'>
                <div
                  className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 transition-all`}
                >
                  {(expanded ? filterItems : filterItems.slice(0, cols - 1)).map(f => (
                <div
                  key={f.key}
                  className='flex items-center'
                >
                  <span
                    className={cn(
                      'shrink-0 mr-2 text-sm font-medium text-foreground whitespace-nowrap text-right',
                      i18n.language?.startsWith('zh') ? 'w-18' : 'w-28',
                    )}
                  >
                    {f.label}:
                  </span>
                  <div className='flex-1 min-w-0'>{f.component}</div>
                </div>
              ),
            )}

            {!expanded && (
              <div className='flex items-center justify-end gap-2'>
                <Button
                  size='sm'
                  variant='outline'
                  onClick={handleReset}
                >
                  {t('module.order.filters.reset')}
                </Button>
                <Button
                  size='sm'
                  onClick={handleSearch}
                >
                  {t('module.order.filters.search')}
                </Button>
                <Button
                  size='sm'
                  variant='ghost'
                  className='px-2 text-primary'
                  onClick={() => setExpanded(true)}
                >
                  {t('common.core.expand', '展开')}
                  <ChevronDown className='ml-1 h-4 w-4' />
                </Button>
              </div>
            )}
          </div>
          {expanded && (
            <div className='mt-4 flex justify-end gap-2'>
              <Button
                size='sm'
                variant='outline'
                onClick={handleReset}
              >
                {t('module.order.filters.reset')}
              </Button>
              <Button
                size='sm'
                onClick={handleSearch}
              >
                {t('module.order.filters.search')}
              </Button>
              <Button
                size='sm'
                variant='ghost'
                className='px-2 text-primary'
                onClick={() => setExpanded(false)}
              >
                {t('common.core.collapse', '收起')}
                <ChevronUp className='ml-1 h-4 w-4' />
              </Button>
            </div>
          )}
        </div>

        <div
          className='flex-1 overflow-auto rounded-xl border border-border bg-white shadow-sm'
          style={{
            minHeight: '420px',
            maxHeight: 'calc(100vh - 280px)',
          }}
        >
          {loading ? (
            <div className='flex items-center justify-center h-40'>
              <Loading />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead
                    className='relative border-r border-border last:border-r-0'
                    style={getColumnStyle('orderId')}
                  >
                    {t('module.order.table.orderId')}
                    {renderResizeHandle('orderId')}
                  </TableHead>
                  <TableHead
                    className='relative border-r border-border last:border-r-0'
                    style={getColumnStyle('shifu')}
                  >
                    {t('module.order.table.shifu')}
                    {renderResizeHandle('shifu')}
                  </TableHead>
                  <TableHead
                    className='relative border-r border-border last:border-r-0'
                    style={getColumnStyle('user')}
                  >
                    {t('module.order.table.user')}
                    {renderResizeHandle('user')}
                  </TableHead>
                  <TableHead
                    className='relative border-r border-border last:border-r-0'
                    style={getColumnStyle('amount')}
                  >
                    {t('module.order.table.amount')}
                    {renderResizeHandle('amount')}
                  </TableHead>
                  <TableHead
                    className='relative border-r border-border last:border-r-0'
                    style={getColumnStyle('status')}
                  >
                    {t('module.order.table.status')}
                    {renderResizeHandle('status')}
                  </TableHead>
                  <TableHead
                    className='relative border-r border-border last:border-r-0'
                    style={getColumnStyle('payment')}
                  >
                    {t('module.order.table.payment')}
                    {renderResizeHandle('payment')}
                  </TableHead>
                  <TableHead
                    className='relative border-r border-border last:border-r-0'
                    style={getColumnStyle('createdAt')}
                  >
                    {t('module.order.table.createdAt')}
                    {renderResizeHandle('createdAt')}
                  </TableHead>
                  <TableHead
                    className='relative border-r border-border last:border-r-0'
                    style={getColumnStyle('action')}
                  >
                    {t('module.order.table.action')}
                    {renderResizeHandle('action')}
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
                    <TableCell
                      className='font-mono text-xs border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                      style={getColumnStyle('orderId')}
                    >
                      {order.order_bid}
                    </TableCell>
                    <TableCell
                      className='whitespace-nowrap border-r border-border last:border-r-0 overflow-hidden text-ellipsis'
                      style={getColumnStyle('shifu')}
                    >
                      <div className='font-medium text-foreground'>
                        {order.shifu_name || order.shifu_bid}
                      </div>
                    </TableCell>
                    <TableCell
                      className='border-r border-border last:border-r-0'
                      style={getColumnStyle('user')}
                    >
                      <div className='font-medium text-foreground whitespace-nowrap overflow-hidden text-ellipsis'>
                        {order.user_mobile || order.user_bid}
                      </div>
                      <div className='text-xs text-muted-foreground whitespace-nowrap overflow-hidden text-ellipsis'>
                        {order.user_nickname || order.user_bid}
                      </div>
                    </TableCell>
                    <TableCell
                      className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                      style={getColumnStyle('amount')}
                    >
                      <div className='font-semibold text-foreground'>
                        {order.payable_price}
                      </div>
                    </TableCell>
                    <TableCell
                      className='whitespace-nowrap border-r border-border last:border-r-0 overflow-hidden text-ellipsis'
                      style={getColumnStyle('status')}
                    >
                      <Badge variant={resolveStatusVariant(order.status)}>
                        {t(order.status_key)}
                      </Badge>
                    </TableCell>
                    <TableCell
                      className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                      style={getColumnStyle('payment')}
                    >
                      <div className='text-sm text-foreground'>
                        {t(order.payment_channel_key)}
                      </div>
                    </TableCell>
                    <TableCell
                      className='text-xs text-muted-foreground whitespace-nowrap border-r border-border last:border-r-0 overflow-hidden text-ellipsis'
                      style={getColumnStyle('createdAt')}
                    >
                      {order.created_at}
                    </TableCell>
                    <TableCell
                      className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                      style={getColumnStyle('action')}
                    >
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

      <ImportActivationDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onSuccess={() => fetchOrders(1)}
      />
    </div>
  );
};

export default OrdersPage;
