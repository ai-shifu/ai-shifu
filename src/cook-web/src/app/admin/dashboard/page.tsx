'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useUserStore } from '@/store';
import type { Shifu } from '@/types/shifu';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
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
import { CalendarIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DashboardOverview } from '@/types/dashboard';
import EChart from '@/components/charts/EChart';
import ChartCard from '@/components/charts/ChartCard';
import { buildBarOption, buildLineOption } from '@/lib/charts/options';

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
  const selectedRange = useMemo(
    () => ({
      from: parseDateValue(startValue),
      to: parseDateValue(endValue),
    }),
    [startValue, endValue],
  );

  const label = useMemo(() => {
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

export default function AdminDashboardPage() {
  const { t } = useTranslation();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);

  const [courses, setCourses] = useState<Shifu[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [coursesError, setCoursesError] = useState<string | null>(null);

  const [shifuBid, setShifuBid] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  const lastFetchedOverviewRef = useRef<{
    shifuBid: string;
    startDate: string;
    endDate: string;
  } | null>(null);

  useEffect(() => {
    if (!isInitialized || isGuest) {
      setCourses([]);
      setCoursesLoading(false);
      setCoursesError(null);
      setShifuBid('');
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
            archived: false,
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
          setShifuBid(prev => prev || collected[0]?.bid || '');
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
    } catch {
      setOverview(null);
      setOverviewError(t('common.core.networkError'));
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

  const completionRateText = useMemo(() => {
    if (!overview) {
      return '-';
    }
    const percent = Math.round((overview.kpis.completion_rate || 0) * 100);
    return `${percent}%`;
  }, [overview]);

  const progressDistributionOption = useMemo(() => {
    const categories =
      overview?.progress_distribution?.map(item => item.label) ?? [];
    const values =
      overview?.progress_distribution?.map(item => item.value) ?? [];
    return buildBarOption({ categories, values });
  }, [overview]);

  const followUpTrendOption = useMemo(() => {
    const x = overview?.follow_up_trend?.map(item => item.label) ?? [];
    const y = overview?.follow_up_trend?.map(item => item.value) ?? [];
    return buildLineOption({ x, y });
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

  return (
    <div className='h-full p-0'>
      <div className='h-full overflow-hidden flex flex-col'>
        <div className='flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-5'>
          <h1 className='text-2xl font-semibold text-gray-900'>
            {t('module.dashboard.title')}
          </h1>
          <div className='flex flex-col gap-3 md:flex-row md:items-center md:justify-end'>
            <div className='flex items-center gap-2'>
              <span className='text-sm text-muted-foreground whitespace-nowrap'>
                {t('common.core.shifu')}
              </span>
              <Select
                value={shifuBid}
                onValueChange={setShifuBid}
                disabled={coursesLoading || courses.length === 0}
              >
                <SelectTrigger className='h-9 w-[240px] max-w-[80vw]'>
                  <SelectValue
                    placeholder={t('module.dashboard.filters.selectCourse')}
                  />
                </SelectTrigger>
                <SelectContent>
                  {courses.map(course => (
                    <SelectItem
                      key={course.bid}
                      value={course.bid}
                    >
                      {course.name || course.bid}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

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
          </div>
        </div>
        {coursesError ? (
          <div className='text-sm text-destructive'>{coursesError}</div>
        ) : null}

        <div className='grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4'>
          <Card>
            <CardContent className='p-4'>
              <div className='text-sm text-muted-foreground'>
                {t('module.dashboard.kpi.learners')}
              </div>
              <div className='mt-2 text-2xl font-semibold text-foreground'>
                {overviewLoading ? '-' : (overview?.kpis.learner_count ?? '-')}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className='p-4'>
              <div className='text-sm text-muted-foreground'>
                {t('module.dashboard.kpi.completionRate')}
              </div>
              <div className='mt-2 text-2xl font-semibold text-foreground'>
                {overviewLoading ? '-' : completionRateText}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className='p-4'>
              <div className='text-sm text-muted-foreground'>
                {t('module.dashboard.kpi.followUps')}
              </div>
              <div className='mt-2 text-2xl font-semibold text-foreground'>
                {overviewLoading
                  ? '-'
                  : (overview?.kpis.follow_up_ask_total ?? '-')}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className='p-4'>
              <div className='text-sm text-muted-foreground'>
                {t('module.dashboard.kpi.requiredOutlines')}
              </div>
              <div className='mt-2 text-2xl font-semibold text-foreground'>
                {overviewLoading
                  ? '-'
                  : (overview?.kpis.required_outline_total ?? '-')}
              </div>
            </CardContent>
          </Card>
        </div>

        {overviewError ? (
          <div className='mt-3 text-sm text-destructive'>{overviewError}</div>
        ) : null}

        <div className='mt-5 grid flex-1 grid-cols-1 gap-3 overflow-auto pb-4 lg:grid-cols-2'>
          <ChartCard title={t('module.dashboard.chart.progressDistribution')}>
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
            className='lg:col-span-2'
          >
            <div className='h-[320px]'>
              <EChart
                option={topOutlinesOption}
                loading={overviewLoading}
                style={{ height: '100%' }}
              />
            </div>
          </ChartCard>
        </div>
      </div>
    </div>
  );
}
