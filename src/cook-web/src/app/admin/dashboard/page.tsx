'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useUserStore } from '@/store';
import { useEnvStore } from '@/c-store';
import { ErrorWithCode } from '@/lib/request';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { Calendar } from '@/components/ui/Calendar';
import { CalendarIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Table,
  TableBody,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';
import type { DateRange } from 'react-day-picker';
import type {
  DashboardEntryCourseItem,
  DashboardEntryResponse,
  DashboardEntrySummary,
} from '@/types/dashboard';
import {
  buildAdminDashboardCourseDetailUrl,
  buildAdminOrdersUrl,
} from './admin-dashboard-routes';
import {
  DashboardCourseTableRow,
  formatOrderAmount,
} from './dashboardCourseTableRow';

const PAGE_SIZE = 20;

const formatDateValue = (value: Date): string => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const parseDateValue = (value: string): Date | undefined => {
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
  const selectedRange = useMemo<DateRange | undefined>(() => {
    const from = parseDateValue(startValue);
    const to = parseDateValue(endValue);
    if (!from && !to) {
      return undefined;
    }
    return { from, to };
  }, [startValue, endValue]);
  const [draftRange, setDraftRange] = useState<DateRange | undefined>(
    selectedRange,
  );

  useEffect(() => {
    setDraftRange(selectedRange);
  }, [selectedRange]);

  const label = useMemo(() => {
    if (draftRange?.from && draftRange?.to) {
      return `${formatDateValue(draftRange.from)} ~ ${formatDateValue(
        draftRange.to,
      )}`;
    }
    if (draftRange?.from) {
      return formatDateValue(draftRange.from);
    }
    return placeholder;
  }, [draftRange?.from, draftRange?.to, placeholder]);

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
              draftRange?.from ? 'text-foreground' : 'text-muted-foreground',
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
          selected={draftRange}
          onSelect={range => {
            const nextRange = range;
            setDraftRange(nextRange);
            if (!nextRange?.from) {
              onChange({ start: '', end: '' });
              return;
            }
            if (nextRange.from && nextRange.to) {
              onChange({
                start: formatDateValue(nextRange.from),
                end: formatDateValue(nextRange.to),
              });
            }
          }}
          className='p-3 md:p-4 [--cell-size:2.4rem]'
        />
        <div className='flex items-center justify-end gap-2 border-t border-border px-3 py-2'>
          <Button
            size='sm'
            variant='ghost'
            type='button'
            onClick={() => {
              setDraftRange(undefined);
              onChange({ start: '', end: '' });
            }}
          >
            {resetLabel}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
};

type ErrorState = { message: string; code?: number };

const EMPTY_SUMMARY: DashboardEntrySummary = {
  course_count: 0,
  learner_count: 0,
  order_count: 0,
  order_amount: '0.00',
};

const DASHBOARD_TABLE_HEAD_CLASS =
  'sticky top-0 z-30 bg-muted border-r border-border last:border-r-0';

export default function AdminDashboardEntryPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const currencySymbol = useEnvStore(state => state.currencySymbol || '¥');

  const [keyword, setKeyword] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const [summary, setSummary] = useState<DashboardEntrySummary>(EMPTY_SUMMARY);
  const [items, setItems] = useState<DashboardEntryCourseItem[]>([]);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [total, setTotal] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);

  const fetchEntry = useCallback(
    async (
      targetPage: number,
      params: { keyword: string; startDate: string; endDate: string },
    ) => {
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getDashboardEntry({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          keyword: params.keyword.trim(),
          start_date: params.startDate,
          end_date: params.endDate,
        })) as DashboardEntryResponse;

        setSummary(response.summary || EMPTY_SUMMARY);
        setItems(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 1);
        setTotal(response.total || 0);
      } catch (err) {
        setSummary(EMPTY_SUMMARY);
        setItems([]);
        setPageIndex(targetPage);
        setPageCount(1);
        setTotal(0);
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
    if (!isInitialized) {
      return;
    }
    if (isGuest) {
      const currentPath = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?redirect=${currentPath}`;
      return;
    }

    fetchEntry(1, { keyword: '', startDate: '', endDate: '' });
  }, [fetchEntry, isGuest, isInitialized]);

  const handleSearch = useCallback(() => {
    fetchEntry(1, {
      keyword,
      startDate,
      endDate,
    });
  }, [endDate, fetchEntry, keyword, startDate]);

  const handleReset = useCallback(() => {
    setKeyword('');
    setStartDate('');
    setEndDate('');
    fetchEntry(1, {
      keyword: '',
      startDate: '',
      endDate: '',
    });
  }, [fetchEntry]);

  const handlePageChange = useCallback(
    (nextPage: number) => {
      if (nextPage < 1 || nextPage > pageCount || nextPage === pageIndex) {
        return;
      }
      fetchEntry(nextPage, {
        keyword,
        startDate,
        endDate,
      });
    },
    [endDate, fetchEntry, keyword, pageCount, pageIndex, startDate],
  );

  const handleOrderClick = useCallback(
    (shifuBid: string) => {
      const nextUrl = buildAdminOrdersUrl(shifuBid);
      if (!nextUrl) {
        return;
      }
      router.push(nextUrl);
    },
    [router],
  );

  const handleCourseDetailClick = useCallback(
    (shifuBid: string) => {
      const nextUrl = buildAdminDashboardCourseDetailUrl(shifuBid);
      if (!nextUrl) {
        return;
      }
      router.push(nextUrl);
    },
    [router],
  );

  if (!isInitialized || isGuest) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Loading />
      </div>
    );
  }

  if (error && !loading && total === 0) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 500}
          errorMessage={error.message}
          onRetry={handleSearch}
        />
      </div>
    );
  }

  return (
    <div className='h-full p-0'>
      <div className='h-full overflow-hidden flex flex-col'>
        <div className='flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-5'>
          <h1 className='text-2xl font-semibold text-gray-900'>
            {t('module.dashboard.title')}
          </h1>
          <div className='flex flex-col gap-2 md:flex-row md:items-center md:justify-end'>
            <Input
              value={keyword}
              onChange={event => setKeyword(event.target.value)}
              placeholder={t('module.dashboard.entry.table.searchPlaceholder')}
              className='h-9 w-[280px] max-w-[80vw]'
            />
            <div className='w-[260px] max-w-[80vw]'>
              <DateRangeFilter
                startValue={startDate}
                endValue={endDate}
                onChange={range => {
                  setStartDate(range.start);
                  setEndDate(range.end);
                }}
                placeholder={t('module.dashboard.filters.dateRangePlaceholder')}
                resetLabel={t('module.dashboard.filters.reset')}
              />
            </div>
            <Button
              size='sm'
              type='button'
              onClick={handleSearch}
            >
              {t('module.dashboard.entry.table.search')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              type='button'
              onClick={handleReset}
            >
              {t('module.dashboard.entry.table.reset')}
            </Button>
          </div>
        </div>

        <div className='shrink-0 mb-5 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4'>
          <Card>
            <CardContent className='p-4'>
              <div className='text-sm text-muted-foreground'>
                {t('module.dashboard.entry.kpi.courses')}
              </div>
              <div className='mt-2 text-2xl font-semibold text-foreground'>
                {loading ? '-' : summary.course_count}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className='p-4'>
              <div className='text-sm text-muted-foreground'>
                {t('module.dashboard.entry.kpi.learners')}
              </div>
              <div className='mt-2 text-2xl font-semibold text-foreground'>
                {loading ? '-' : summary.learner_count}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className='p-4'>
              <div className='text-sm text-muted-foreground'>
                {t('module.dashboard.entry.kpi.orders')}
              </div>
              <div className='mt-2 text-2xl font-semibold text-foreground'>
                {loading ? '-' : summary.order_count}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className='p-4'>
              <div className='text-sm text-muted-foreground'>
                {t('module.dashboard.entry.kpi.orderAmount')}
              </div>
              <div className='mt-2 text-2xl font-semibold text-foreground'>
                {loading
                  ? '-'
                  : formatOrderAmount(summary.order_amount, currencySymbol)}
              </div>
            </CardContent>
          </Card>
        </div>

        {error ? (
          <div className='shrink-0 mb-4 text-sm text-destructive'>
            {error.message}
          </div>
        ) : null}

        <div className='flex-1 min-h-0 flex flex-col'>
          <div className='flex min-h-0 flex-1 flex-col rounded-xl border border-border bg-white shadow-sm'>
            <div className='shrink-0 border-b border-border p-4'>
              <div className='flex items-baseline gap-2'>
                <h2 className='text-base font-semibold text-foreground'>
                  {t('module.dashboard.entry.table.title')}
                </h2>
                <span className='text-sm text-muted-foreground'>
                  {t('module.dashboard.entry.table.totalCount', {
                    count: total,
                  })}
                </span>
              </div>
            </div>

            <div
              data-testid='dashboard-course-list-scroll-region'
              className='min-h-0 flex-1 overflow-hidden'
            >
              {loading ? (
                <div className='flex h-full min-h-40 items-center justify-center'>
                  <Loading />
                </div>
              ) : (
                <Table
                  containerClassName='h-full'
                  className='min-w-[820px]'
                >
                  <TableHeader>
                    <TableRow>
                      <TableHead
                        className={cn(
                          DASHBOARD_TABLE_HEAD_CLASS,
                          'min-w-[280px]',
                        )}
                      >
                        {t('module.dashboard.entry.table.course')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          DASHBOARD_TABLE_HEAD_CLASS,
                          'min-w-[120px]',
                        )}
                      >
                        {t('module.dashboard.entry.table.learners')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          DASHBOARD_TABLE_HEAD_CLASS,
                          'min-w-[120px]',
                        )}
                      >
                        {t('module.dashboard.entry.table.orders')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          DASHBOARD_TABLE_HEAD_CLASS,
                          'min-w-[140px]',
                        )}
                      >
                        {t('module.dashboard.entry.table.orderAmount')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          DASHBOARD_TABLE_HEAD_CLASS,
                          'min-w-[180px]',
                        )}
                      >
                        {t('module.dashboard.entry.table.lastActive')}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.length === 0 ? (
                      <TableEmpty colSpan={5}>
                        {t('module.dashboard.entry.table.empty')}
                      </TableEmpty>
                    ) : null}

                    {items.map(item => (
                      <DashboardCourseTableRow
                        key={item.shifu_bid}
                        item={item}
                        currencySymbol={currencySymbol}
                        orderButtonLabel={`${t('module.dashboard.entry.table.orders')}-${item.shifu_bid}`}
                        onCourseDetailClick={handleCourseDetailClick}
                        onOrderClick={handleOrderClick}
                      />
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>

          <div
            data-testid='dashboard-course-list-footer'
            className='mt-4 flex shrink-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between'
          >
            <p className='min-w-0 flex-1 text-sm text-muted-foreground'>
              {t('module.dashboard.entry.table.scopeNote')}
            </p>

            <Pagination className='mx-0 w-full justify-start sm:w-auto sm:shrink-0 sm:justify-end'>
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious
                    href='#'
                    onClick={event => {
                      event.preventDefault();
                      handlePageChange(pageIndex - 1);
                    }}
                    aria-disabled={pageIndex <= 1}
                    className={
                      pageIndex <= 1 ? 'pointer-events-none opacity-50' : ''
                    }
                  >
                    {t('module.dashboard.pagination.prev')}
                  </PaginationPrevious>
                </PaginationItem>

                {(() => {
                  const startPage =
                    pageCount <= 5
                      ? 1
                      : Math.max(1, Math.min(pageIndex - 2, pageCount - 4));
                  const endPage =
                    pageCount <= 5
                      ? pageCount
                      : Math.min(pageCount, startPage + 4);

                  const pages: number[] = [];
                  for (let page = startPage; page <= endPage; page += 1) {
                    pages.push(page);
                  }

                  return pages.map(page => (
                    <PaginationItem key={page}>
                      <PaginationLink
                        href='#'
                        onClick={event => {
                          event.preventDefault();
                          handlePageChange(page);
                        }}
                        isActive={page === pageIndex}
                      >
                        {page}
                      </PaginationLink>
                    </PaginationItem>
                  ));
                })()}

                <PaginationItem>
                  <PaginationNext
                    href='#'
                    onClick={event => {
                      event.preventDefault();
                      handlePageChange(pageIndex + 1);
                    }}
                    aria-disabled={pageIndex >= pageCount}
                    className={
                      pageIndex >= pageCount
                        ? 'pointer-events-none opacity-50'
                        : ''
                    }
                  >
                    {t('module.dashboard.pagination.next')}
                  </PaginationNext>
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          </div>
        </div>
      </div>
    </div>
  );
}
