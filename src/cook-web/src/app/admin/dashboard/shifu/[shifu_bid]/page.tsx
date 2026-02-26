'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import api from '@/api';
import { useUserStore } from '@/store';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { Calendar } from '@/components/ui/Calendar';
import { ArrowLeft, CalendarIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ErrorWithCode } from '@/lib/request';
import type { DashboardOverview } from '@/types/dashboard';
import EChart from '@/components/charts/EChart';
import ChartCard from '@/components/charts/ChartCard';
import { buildBarOption } from '@/lib/charts/options';
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { toast } from '@/hooks/useToast';
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';
import type { DateRange } from 'react-day-picker';
import type { DashboardLearnerSummary, DashboardPage } from '@/types/dashboard';

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

const buildRequestId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replace(/-/g, '');
  }
  return `${Date.now()}${Math.random().toString(36).slice(2, 10)}`;
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

export default function AdminDashboardPage() {
  const { t } = useTranslation();
  const params = useParams<{ shifu_bid?: string | string[] }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const urlStartDate = searchParams.get('start_date') || '';
  const urlEndDate = searchParams.get('end_date') || '';

  const shifuBid = useMemo(() => {
    const value = params?.shifu_bid;
    if (Array.isArray(value)) {
      return value[0] || '';
    }
    return value || '';
  }, [params]);
  const [startDate, setStartDate] = useState(
    () => urlStartDate,
  );
  const [endDate, setEndDate] = useState(
    () => urlEndDate,
  );

  useEffect(() => {
    setStartDate(previous => (previous === urlStartDate ? previous : urlStartDate));
    setEndDate(previous => (previous === urlEndDate ? previous : urlEndDate));
  }, [urlEndDate, urlStartDate]);

  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<ErrorState | null>(null);

  const [learnerKeyword, setLearnerKeyword] = useState('');
  const [learnerSort, setLearnerSort] = useState('last_active_desc');

  const [learners, setLearners] = useState<DashboardLearnerSummary[]>([]);
  const [learnerPageIndex, setLearnerPageIndex] = useState(1);
  const [learnerPageCount, setLearnerPageCount] = useState(1);
  const [learnerTotal, setLearnerTotal] = useState(0);
  const [learnersLoading, setLearnersLoading] = useState(false);
  const [learnersError, setLearnersError] = useState<ErrorState | null>(null);
  const [exporting, setExporting] = useState(false);
  const defaultUserName = useMemo(() => t('module.user.defaultUserName'), [t]);

  const lastFetchedOverviewRef = useRef<{
    shifuBid: string;
    startDate: string;
    endDate: string;
  } | null>(null);

  useEffect(() => {
    if (!isInitialized) {
      return;
    }
    if (isGuest) {
      const currentPath = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?redirect=${currentPath}`;
    }
  }, [isInitialized, isGuest]);

  const fetchOverview = useCallback(async () => {
    if (!shifuBid) {
      setOverview(null);
      setOverviewLoading(false);
      setOverviewError(null);
      return;
    }

    const cached = lastFetchedOverviewRef.current;
    if (
      overview &&
      cached?.shifuBid === shifuBid &&
      cached?.startDate === startDate &&
      cached?.endDate === endDate
    ) {
      return;
    }

    setOverviewLoading(true);
    setOverviewError(null);
    try {
      const result = (await api.getDashboardOverview({
        shifu_bid: shifuBid,
        start_date: startDate,
        end_date: endDate,
      })) as DashboardOverview;
      setOverview(result);

      lastFetchedOverviewRef.current = {
        shifuBid,
        startDate: result.start_date || startDate,
        endDate: result.end_date || endDate,
      };

      if (result.start_date && result.start_date !== startDate) {
        setStartDate(result.start_date);
      }
      if (result.end_date && result.end_date !== endDate) {
        setEndDate(result.end_date);
      }
    } catch (err) {
      setOverview(null);
      if (err instanceof ErrorWithCode) {
        setOverviewError({ message: err.message, code: err.code });
      } else if (err instanceof Error) {
        setOverviewError({ message: err.message });
      } else {
        setOverviewError({ message: t('common.core.unknownError') });
      }
    } finally {
      setOverviewLoading(false);
    }
  }, [endDate, overview, shifuBid, startDate, t]);

  useEffect(() => {
    if (!isInitialized || isGuest) {
      setOverview(null);
      setOverviewLoading(false);
      setOverviewError(null);
      return;
    }
    fetchOverview();
  }, [fetchOverview, isInitialized, isGuest]);

  const fetchLearners = useCallback(
    async (targetPage: number, params: { keyword: string; sort: string }) => {
      if (!shifuBid) {
        setLearners([]);
        setLearnerPageIndex(1);
        setLearnerPageCount(1);
        setLearnerTotal(0);
        setLearnersLoading(false);
        setLearnersError(null);
        return;
      }

      setLearnersLoading(true);
      setLearnersError(null);
      try {
        const response = (await api.getDashboardLearners({
          shifu_bid: shifuBid,
          page_index: targetPage,
          page_size: 20,
          keyword: params.keyword.trim(),
          sort: params.sort,
        })) as DashboardPage<DashboardLearnerSummary>;

        setLearners(response.items || []);
        setLearnerPageIndex(response.page || targetPage);
        setLearnerPageCount(response.page_count || 1);
        setLearnerTotal(response.total || 0);
      } catch (err) {
        setLearners([]);
        setLearnerPageIndex(targetPage);
        setLearnerPageCount(1);
        setLearnerTotal(0);
        if (err instanceof ErrorWithCode) {
          setLearnersError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setLearnersError({ message: err.message });
        } else {
          setLearnersError({ message: t('common.core.unknownError') });
        }
      } finally {
        setLearnersLoading(false);
      }
    },
    [shifuBid, t],
  );

  useEffect(() => {
    if (!isInitialized || isGuest) {
      setLearnerKeyword('');
      setLearnerSort('last_active_desc');
      setLearners([]);
      setLearnerPageIndex(1);
      setLearnerPageCount(1);
      setLearnerTotal(0);
      setLearnersLoading(false);
      setLearnersError(null);
      return;
    }
    if (!shifuBid) {
      setLearners([]);
      setLearnerPageIndex(1);
      setLearnerPageCount(1);
      setLearnerTotal(0);
      setLearnersLoading(false);
      setLearnersError(null);
      return;
    }

    const defaultSort = 'last_active_desc';
    setLearnerKeyword('');
    setLearnerSort(defaultSort);
    fetchLearners(1, { keyword: '', sort: defaultSort });
  }, [fetchLearners, isInitialized, isGuest, shifuBid]);

  const progressDistributionOption = useMemo(() => {
    const categories =
      overview?.progress_distribution?.map(item => item.label) ?? [];
    const values =
      overview?.progress_distribution?.map(item => item.value) ?? [];
    return buildBarOption({ categories, values });
  }, [overview]);

  const followUpTrendOption = useMemo(() => {
    const categories = overview?.follow_up_trend?.map(item => item.label) ?? [];
    const values = overview?.follow_up_trend?.map(item => item.value) ?? [];
    const option = buildBarOption({ categories, values });
    const xAxis = (option as any).xAxis ?? {};
    const axisLabel = xAxis.axisLabel ?? {};
    const interval =
      categories.length > 8 ? Math.ceil(categories.length / 8) - 1 : 0;
    (option as any).xAxis = {
      ...xAxis,
      axisLabel: {
        ...axisLabel,
        interval,
        rotate: categories.length > 12 ? 30 : 0,
        formatter: (value: string) =>
          value && value.length >= 10 ? value.slice(5) : value,
      },
    };
    return option;
  }, [overview]);

  const topOutlinesOption = useMemo(() => {
    const categories =
      overview?.top_outlines_by_follow_ups?.map(item => item.title) ?? [];
    const values =
      overview?.top_outlines_by_follow_ups?.map(item => item.ask_count) ?? [];
    const option = buildBarOption({ categories, values });

    const xAxis = (option as any).xAxis ?? {};
    const axisLabel = xAxis.axisLabel ?? {};
    (option as any).xAxis = {
      ...xAxis,
      axisLabel: {
        ...axisLabel,
        rotate: categories.length > 5 ? 30 : 0,
        formatter: (value: string) =>
          value && value.length > 12 ? `${value.slice(0, 12)}...` : value,
      },
    };

    return option;
  }, [overview]);

  const chapterDistributionOption = useMemo(() => {
    const categories =
      overview?.follow_up_chapter_distribution?.map(item => item.label) ?? [];
    const values =
      overview?.follow_up_chapter_distribution?.map(item => item.value) ?? [];
    const option = buildBarOption({ categories, values });

    const xAxis = (option as any).xAxis ?? {};
    const axisLabel = xAxis.axisLabel ?? {};
    (option as any).xAxis = {
      ...xAxis,
      axisLabel: {
        ...axisLabel,
        rotate: categories.length > 5 ? 30 : 0,
        formatter: (value: string) =>
          value && value.length > 12 ? `${value.slice(0, 12)}...` : value,
      },
    };

    return option;
  }, [overview]);

  const formatLastActive = useCallback((value: string) => {
    if (!value) {
      return '-';
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleString();
  }, []);

  const handleExport = useCallback(async () => {
    if (!shifuBid || exporting) {
      return;
    }
    setExporting(true);
    try {
      const query = new URLSearchParams();
      if (startDate) {
        query.set('start_date', startDate);
      }
      if (endDate) {
        query.set('end_date', endDate);
      }

      const token = useUserStore.getState().getToken() || '';
      const headers: Record<string, string> = {
        'X-Request-ID': buildRequestId(),
      };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
        headers.Token = token;
      }

      const queryString = query.toString();
      const endpoint = `/api/dashboard/shifus/${encodeURIComponent(shifuBid)}/export`;
      const url = queryString ? `${endpoint}?${queryString}` : endpoint;
      const response = await fetch(url, { method: 'GET', headers });
      const contentType = response.headers.get('Content-Type') || '';
      if (contentType.includes('application/json')) {
        const payload = await response.json();
        const message =
          payload && typeof payload.message === 'string'
            ? payload.message
            : t('module.dashboard.export.error');
        throw new Error(message);
      }
      if (!response.ok) {
        throw new Error(t('module.dashboard.export.error'));
      }

      const blob = await response.blob();
      const contentDisposition = response.headers.get('Content-Disposition') || '';
      let filename = `${shifuBid}-dashboard-export.xlsx`;
      const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
      if (utf8Match && utf8Match[1]) {
        filename = decodeURIComponent(utf8Match[1]);
      } else {
        const filenameMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
        if (filenameMatch && filenameMatch[1]) {
          filename = filenameMatch[1];
        }
      }

      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.URL.revokeObjectURL(objectUrl);
    } catch (error) {
      toast({
        title:
          error instanceof Error
            ? error.message
            : t('module.dashboard.export.error'),
        variant: 'destructive',
      });
    } finally {
      setExporting(false);
    }
  }, [endDate, exporting, shifuBid, startDate, t]);

  const handleLearnerPageChange = (nextPage: number) => {
    if (
      nextPage < 1 ||
      nextPage > learnerPageCount ||
      nextPage === learnerPageIndex
    ) {
      return;
    }
    fetchLearners(nextPage, { keyword: learnerKeyword, sort: learnerSort });
  };

  const handleBackToEntry = useCallback(() => {
    if (typeof window !== 'undefined' && window.history.length > 1) {
      router.back();
      return;
    }
    router.push('/admin/dashboard');
  }, [router]);

  const buildLearnerDetailHref = useCallback(
    (userBid: string) => {
      const query = new URLSearchParams();
      if (startDate) {
        query.set('start_date', startDate);
      }
      if (endDate) {
        query.set('end_date', endDate);
      }
      const queryText = query.toString();
      const basePath = `/admin/dashboard/shifu/${shifuBid}/learners/${userBid}`;
      return queryText ? `${basePath}?${queryText}` : basePath;
    },
    [endDate, shifuBid, startDate],
  );

  if (!isInitialized) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Loading />
      </div>
    );
  }

  if (isGuest) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Loading />
      </div>
    );
  }

  return (
    <div className='h-full p-0'>
      <div className='h-full overflow-hidden flex flex-col'>
        <div className='flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-5'>
          <div className='flex items-center gap-3'>
            <Button
              size='sm'
              variant='outline'
              type='button'
              onClick={handleBackToEntry}
            >
              <ArrowLeft className='mr-1 h-4 w-4' />
              {t('module.dashboard.actions.back')}
            </Button>
            <h1 className='text-2xl font-semibold text-gray-900 break-all'>
              {t('module.dashboard.title')}
              {overview?.shifu_name ? (
                <span className='ml-2 text-sm font-normal text-muted-foreground'>
                  {overview.shifu_name}
                </span>
              ) : null}
            </h1>
          </div>
          <div className='flex flex-col gap-3 md:flex-row md:items-center md:justify-end'>
            <div className='flex items-center gap-2'>
              <span className='text-sm text-muted-foreground whitespace-nowrap'>
                {t('module.dashboard.filters.dateRange')}
              </span>
              <div className='w-[260px] max-w-[80vw]'>
                <DateRangeFilter
                  startValue={startDate}
                  endValue={endDate}
                  onChange={range => {
                    setStartDate(range.start);
                    setEndDate(range.end);
                  }}
                  placeholder={t(
                    'module.dashboard.filters.dateRangePlaceholder',
                  )}
                  resetLabel={t('module.dashboard.filters.reset')}
                />
              </div>
            </div>
            <Button
              size='sm'
              variant='outline'
              type='button'
              onClick={handleExport}
              disabled={exporting || !shifuBid}
            >
              {exporting
                ? t('module.dashboard.export.loading')
                : t('module.dashboard.export.button')}
            </Button>
          </div>
        </div>

        <div className='flex-1 overflow-auto pb-4 space-y-5'>
          {overviewError && !overviewLoading && !overview ? (
            <ErrorDisplay
              errorCode={overviewError.code || 500}
              errorMessage={overviewError.message}
              onRetry={fetchOverview}
            />
          ) : (
            <>
              <div className='grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4'>
                <Card>
                  <CardContent className='p-4'>
                    <div className='text-sm text-muted-foreground'>
                      {t('module.dashboard.entry.kpi.learners')}
                    </div>
                    <div className='mt-2 text-2xl font-semibold text-foreground'>
                      {overviewLoading
                        ? '-'
                        : (overview?.kpis.learner_count ?? '-')}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className='p-4'>
                    <div className='text-sm text-muted-foreground'>
                      {t('module.dashboard.entry.kpi.orders')}
                    </div>
                    <div className='mt-2 text-2xl font-semibold text-foreground'>
                      {overviewLoading ? '-' : (overview?.kpis.order_count ?? '-')}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className='p-4'>
                    <div className='text-sm text-muted-foreground'>
                      {t('module.dashboard.entry.kpi.generations')}
                    </div>
                    <div className='mt-2 text-2xl font-semibold text-foreground'>
                      {overviewLoading
                        ? '-'
                        : (overview?.kpis.generation_count ?? '-')}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className='p-4'>
                    <div className='text-sm text-muted-foreground'>
                      {t('module.dashboard.entry.table.lastActive')}
                    </div>
                    <div className='mt-2 text-2xl font-semibold text-foreground'>
                      {overviewLoading
                        ? '-'
                        : formatLastActive(overview?.kpis.last_active_at || '')}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {overviewError ? (
                <div className='text-sm text-destructive'>
                  {overviewError.message}
                </div>
              ) : null}

              <div className='grid grid-cols-1 gap-3 lg:grid-cols-2'>
                <ChartCard
                  title={t('module.dashboard.chart.progressDistribution')}
                >
                  <div className='h-[280px]'>
                    <EChart
                      option={progressDistributionOption}
                      loading={overviewLoading}
                      style={{ height: '100%' }}
                    />
                  </div>
                </ChartCard>

                <ChartCard title={t('module.dashboard.chart.followUpsTrend')}>
                  <div className='h-[280px]'>
                    <EChart
                      option={followUpTrendOption}
                      loading={overviewLoading}
                      style={{ height: '100%' }}
                    />
                  </div>
                </ChartCard>

                <ChartCard
                  title={t('module.dashboard.chart.topOutlinesByFollowUps')}
                >
                  <div className='h-[320px]'>
                    <EChart
                      option={topOutlinesOption}
                      loading={overviewLoading}
                      style={{ height: '100%' }}
                    />
                  </div>
                </ChartCard>

                <ChartCard
                  title={t('module.dashboard.chart.followUpsByChapter')}
                >
                  <div className='h-[320px]'>
                    <EChart
                      option={chapterDistributionOption}
                      loading={overviewLoading}
                      style={{ height: '100%' }}
                    />
                  </div>
                </ChartCard>
              </div>
            </>
          )}

          <Card>
            <CardContent className='p-4'>
              <div className='flex flex-col gap-3 md:flex-row md:items-center md:justify-between'>
                <div className='flex items-baseline gap-2'>
                  <h2 className='text-base font-semibold text-foreground'>
                    {t('module.dashboard.table.title')}
                  </h2>
                  <span className='text-sm text-muted-foreground'>
                    {t('module.dashboard.table.totalCount', {
                      count: learnerTotal,
                    })}
                  </span>
                </div>

                <div className='flex flex-col gap-2 md:flex-row md:items-center md:justify-end'>
                  <Input
                    value={learnerKeyword}
                    onChange={event => setLearnerKeyword(event.target.value)}
                    placeholder={t('module.dashboard.table.keywordPlaceholder')}
                    className='h-9 w-[260px] max-w-[80vw]'
                  />

                  <Select
                    value={learnerSort}
                    onValueChange={value => {
                      setLearnerSort(value);
                      fetchLearners(1, {
                        keyword: learnerKeyword,
                        sort: value,
                      });
                    }}
                  >
                    <SelectTrigger className='h-9 w-[200px] max-w-[80vw]'>
                      <SelectValue
                        placeholder={t('module.dashboard.table.sort')}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='last_active_desc'>
                        {t('module.dashboard.sort.lastActive')}
                      </SelectItem>
                      <SelectItem value='progress_desc'>
                        {t('module.dashboard.sort.progress')}
                      </SelectItem>
                      <SelectItem value='followups_desc'>
                        {t('module.dashboard.sort.followUps')}
                      </SelectItem>
                    </SelectContent>
                  </Select>

                  <div className='flex items-center gap-2'>
                    <Button
                      size='sm'
                      type='button'
                      onClick={() =>
                        fetchLearners(1, {
                          keyword: learnerKeyword,
                          sort: learnerSort,
                        })
                      }
                    >
                      {t('module.dashboard.table.search')}
                    </Button>
                    <Button
                      size='sm'
                      variant='outline'
                      type='button'
                      onClick={() => {
                        const defaultSort = 'last_active_desc';
                        setLearnerKeyword('');
                        setLearnerSort(defaultSort);
                        fetchLearners(1, { keyword: '', sort: defaultSort });
                      }}
                    >
                      {t('module.dashboard.table.reset')}
                    </Button>
                  </div>
                </div>
              </div>

              {learnersError && !learnersLoading && learners.length === 0 ? (
                <ErrorDisplay
                  errorCode={learnersError.code || 500}
                  errorMessage={learnersError.message}
                  onRetry={() =>
                    fetchLearners(1, {
                      keyword: learnerKeyword,
                      sort: learnerSort,
                    })
                  }
                />
              ) : (
                <>
                  {learnersError ? (
                    <div className='mt-3 text-sm text-destructive'>
                      {learnersError.message}
                    </div>
                  ) : null}

                  <div className='mt-4 overflow-auto rounded-lg border border-border bg-white'>
                    {learnersLoading ? (
                      <div className='flex h-40 items-center justify-center'>
                        <Loading />
                      </div>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>
                              {t('module.dashboard.table.user')}
                            </TableHead>
                            <TableHead>
                              {t('module.dashboard.table.progress')}
                            </TableHead>
                            <TableHead>
                              {t('module.dashboard.table.followUps')}
                            </TableHead>
                            <TableHead>
                              {t('module.dashboard.table.lastActive')}
                            </TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {learners.length === 0 && (
                            <TableEmpty colSpan={4}>
                              {t('module.dashboard.table.empty')}
                            </TableEmpty>
                          )}
                          {learners.map(item => {
                            const completed = item.completed_outline_count ?? 0;
                            const total = item.required_outline_total ?? 0;
                            const percent = Math.round(
                              (item.progress_percent || 0) * 100,
                            );
                            const progressText =
                              total > 0
                                ? `${completed}/${total} (${percent}%)`
                                : `- (${percent}%)`;
                            return (
                              <TableRow
                                key={item.user_bid}
                                className='cursor-pointer'
                                onClick={() =>
                                  router.push(
                                    buildLearnerDetailHref(item.user_bid),
                                  )
                                }
                              >
                                <TableCell className='whitespace-nowrap'>
                                  <div className='text-sm text-foreground'>
                                    {item.mobile || item.user_bid}
                                  </div>
                                  <div className='text-xs text-muted-foreground'>
                                    {item.nickname || defaultUserName}
                                  </div>
                                </TableCell>
                                <TableCell className='whitespace-nowrap'>
                                  {progressText}
                                </TableCell>
                                <TableCell className='whitespace-nowrap'>
                                  {item.follow_up_ask_count ?? 0}
                                </TableCell>
                                <TableCell className='whitespace-nowrap'>
                                  {formatLastActive(item.last_active_at)}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    )}
                  </div>

                  <div className='mt-4 flex justify-end'>
                    <Pagination className='justify-end w-auto mx-0'>
                      <PaginationContent>
                        <PaginationItem>
                          <PaginationPrevious
                            href='#'
                            onClick={event => {
                              event.preventDefault();
                              handleLearnerPageChange(learnerPageIndex - 1);
                            }}
                            aria-disabled={learnerPageIndex <= 1}
                            className={
                              learnerPageIndex <= 1
                                ? 'pointer-events-none opacity-50'
                                : ''
                            }
                          >
                            {t('module.dashboard.pagination.prev')}
                          </PaginationPrevious>
                        </PaginationItem>

                        {(() => {
                          const startPage =
                            learnerPageCount <= 5
                              ? 1
                              : Math.max(
                                  1,
                                  Math.min(
                                    learnerPageIndex - 2,
                                    learnerPageCount - 4,
                                  ),
                                );
                          const endPage =
                            learnerPageCount <= 5
                              ? learnerPageCount
                              : Math.min(learnerPageCount, startPage + 4);

                          const pages: number[] = [];
                          for (
                            let page = startPage;
                            page <= endPage;
                            page += 1
                          ) {
                            pages.push(page);
                          }

                          return pages.map(page => (
                            <PaginationItem key={page}>
                              <PaginationLink
                                href='#'
                                onClick={event => {
                                  event.preventDefault();
                                  handleLearnerPageChange(page);
                                }}
                                isActive={page === learnerPageIndex}
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
                              handleLearnerPageChange(learnerPageIndex + 1);
                            }}
                            aria-disabled={learnerPageIndex >= learnerPageCount}
                            className={
                              learnerPageIndex >= learnerPageCount
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
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
