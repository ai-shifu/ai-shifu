'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import type { EChartsOption } from 'echarts';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import ChartCard from '@/components/charts/ChartCard';
import EChart from '@/components/charts/EChart';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/Breadcrumb';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Table,
  TableBody,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { ErrorWithCode } from '@/lib/request';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { useUserStore } from '@/store';
import type {
  DashboardCourseDetailFollowUpCountBySection,
  DashboardCourseDetailResponse,
} from '@/types/dashboard';
import { buildAdminOrdersUrl } from '../admin-dashboard-routes';
import { formatOrderAmount } from '../dashboardCourseTableRow';

type ErrorState = { message: string; code?: number };
type FollowUpSectionChartRow = {
  key: string;
  chapterTitle: string;
  sectionTitle: string;
  label: string;
  followUpCount: number;
  isOther?: boolean;
  isUnassigned?: boolean;
};

const EMPTY_DETAIL: DashboardCourseDetailResponse = {
  basic_info: {
    shifu_bid: '',
    course_name: '',
    created_at: '',
    chapter_count: 0,
    learner_count: 0,
  },
  metrics: {
    order_count: 0,
    order_amount: '0.00',
    completed_learner_count: 0,
    completion_rate: '0.00',
    active_learner_count_last_7_days: 0,
    total_follow_up_count: 0,
    avg_follow_up_count_per_learner: '0.00',
    avg_learning_duration_seconds: 0,
  },
  charts: {
    follow_up_count_by_section: [],
  },
};

const ALL_CHAPTER_FILTER_VALUE = '__all__';
const FOLLOW_UP_SECTION_TOP_LIMIT = 20;
const MAX_AXIS_LABEL_LENGTH = 18;

const truncateChartLabel = (value: string): string => {
  if (value.length <= MAX_AXIS_LABEL_LENGTH) {
    return value;
  }
  return `${value.slice(0, MAX_AXIS_LABEL_LENGTH)}...`;
};

const formatDateTime = (
  value: string,
  emptyValue: string,
  displayValue?: string,
): string => {
  if (displayValue) {
    return displayValue;
  }
  if (!value) {
    return emptyValue;
  }
  return value;
};

const formatCount = (value: number, emptyValue: string): string => {
  if (!Number.isFinite(value)) {
    return emptyValue;
  }
  return value.toLocaleString();
};

const formatPercent = (value: string, emptyValue: string): string => {
  const normalized = (value || '').trim();
  if (!normalized) {
    return emptyValue;
  }
  return `${normalized}%`;
};

const formatDuration = (seconds: number): string => {
  const normalizedSeconds =
    Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const hours = Math.floor(normalizedSeconds / 3600);
  const minutes = Math.floor((normalizedSeconds % 3600) / 60);
  const remainingSeconds = normalizedSeconds % 60;
  return [hours, minutes, remainingSeconds]
    .map(part => String(part).padStart(2, '0'))
    .join(':');
};

const buildFollowUpSectionChartOption = (
  rows: FollowUpSectionChartRow[],
  valueName: string,
): EChartsOption => {
  const orderedRows = [...rows].reverse();
  const shouldScroll = orderedRows.length > 12;

  return {
    grid: {
      top: 16,
      left: 28,
      right: shouldScroll ? 54 : 28,
      bottom: 24,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: params => {
        const firstParam = Array.isArray(params) ? params[0] : params;
        const dataIndex =
          typeof firstParam === 'object' &&
          firstParam !== null &&
          'dataIndex' in firstParam
            ? Number(firstParam.dataIndex)
            : 0;
        const row = orderedRows[dataIndex];
        if (!row) {
          return '';
        }
        if (row.isOther) {
          return `${row.sectionTitle}<br/>${valueName}: ${row.followUpCount}`;
        }
        if (row.isUnassigned) {
          return `${row.sectionTitle}<br/>${valueName}: ${row.followUpCount}`;
        }
        return `${row.chapterTitle} / ${row.sectionTitle}<br/>${valueName}: ${row.followUpCount}`;
      },
    },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#eef2f7' } },
      axisLabel: { color: '#64748b' },
    },
    yAxis: {
      type: 'category',
      data: orderedRows.map(row => truncateChartLabel(row.label)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#475569' },
    },
    dataZoom: shouldScroll
      ? [
          {
            type: 'slider',
            yAxisIndex: 0,
            width: 14,
            right: 8,
            startValue: Math.max(orderedRows.length - 12, 0),
            endValue: orderedRows.length - 1,
            filterMode: 'none',
          },
          {
            type: 'inside',
            yAxisIndex: 0,
            filterMode: 'none',
          },
        ]
      : undefined,
    series: [
      {
        type: 'bar',
        name: valueName,
        data: orderedRows.map(row => row.followUpCount),
        barMaxWidth: 22,
        label: {
          show: true,
          position: 'right',
          color: '#334155',
        },
        itemStyle: {
          color: '#2563eb',
          borderRadius: [0, 6, 6, 0],
        },
      },
    ],
  };
};

export default function AdminDashboardCourseDetailPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams<{ shifu_bid?: string }>();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const currencySymbol = useEnvStore(state => state.currencySymbol || '¥');
  const timezone = getBrowserTimeZone();

  const [detail, setDetail] =
    useState<DashboardCourseDetailResponse>(EMPTY_DETAIL);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [selectedFollowUpChapter, setSelectedFollowUpChapter] = useState(
    ALL_CHAPTER_FILTER_VALUE,
  );

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = '--';
  const orderListUrl = buildAdminOrdersUrl(shifuBid);

  const placeholderChartLabels = [
    t('module.dashboard.detail.charts.questionsByTime'),
    t('module.dashboard.detail.charts.learningTrend'),
    t('module.dashboard.detail.charts.chapterProgress'),
  ];
  const learnerTableColumnLabels = [
    t('module.dashboard.detail.learners.columns.name'),
    t('module.dashboard.detail.learners.columns.progress'),
    t('module.dashboard.detail.learners.columns.questions'),
    t('module.dashboard.detail.learners.columns.lastActiveAt'),
  ];

  const fetchDetail = useCallback(async () => {
    if (!shifuBid.trim()) {
      setError({ message: t('common.core.unknownError') });
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = (await api.getDashboardCourseDetail({
        shifu_bid: shifuBid,
        ...(timezone ? { timezone } : {}),
      })) as DashboardCourseDetailResponse;
      setDetail(response || EMPTY_DETAIL);
    } catch (err) {
      setDetail(EMPTY_DETAIL);
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
  }, [shifuBid, t, timezone]);

  useEffect(() => {
    if (!isInitialized || !isGuest) {
      return;
    }

    const currentPath = encodeURIComponent(
      window.location.pathname + window.location.search,
    );
    window.location.href = `/login?redirect=${currentPath}`;
  }, [isGuest, isInitialized]);

  useEffect(() => {
    if (!isInitialized || isGuest) {
      return;
    }
    fetchDetail();
  }, [fetchDetail, isGuest, isInitialized]);

  const handleOrderClick = useCallback(() => {
    if (!orderListUrl) {
      return;
    }
    router.push(orderListUrl);
  }, [orderListUrl, router]);

  const metricCards = useMemo(
    () => [
      {
        label: t('module.dashboard.detail.metrics.orderCount'),
        value: formatCount(detail.metrics.order_count, emptyValue),
        onClick: orderListUrl ? handleOrderClick : undefined,
      },
      {
        label: t('module.dashboard.detail.metrics.orderAmount'),
        value: formatOrderAmount(detail.metrics.order_amount, currencySymbol),
        onClick: orderListUrl ? handleOrderClick : undefined,
      },
      {
        label: t('module.dashboard.detail.metrics.completedLearners'),
        value: formatCount(detail.metrics.completed_learner_count, emptyValue),
      },
      {
        label: t('module.dashboard.detail.metrics.completionRate'),
        value: formatPercent(detail.metrics.completion_rate, emptyValue),
      },
      {
        label: t('module.dashboard.detail.metrics.activeLearnersLast7Days'),
        value: formatCount(
          detail.metrics.active_learner_count_last_7_days,
          emptyValue,
        ),
      },
      {
        label: t('module.dashboard.detail.metrics.totalQuestions'),
        value: formatCount(detail.metrics.total_follow_up_count, emptyValue),
      },
      {
        label: t('module.dashboard.detail.metrics.avgQuestionsPerLearner'),
        value: detail.metrics.avg_follow_up_count_per_learner || emptyValue,
      },
      {
        label: t('module.dashboard.detail.metrics.avgLearningDuration'),
        value: formatDuration(detail.metrics.avg_learning_duration_seconds),
      },
    ],
    [
      currencySymbol,
      detail.metrics,
      emptyValue,
      handleOrderClick,
      orderListUrl,
      t,
    ],
  );

  const followUpSections = useMemo(
    () => detail.charts?.follow_up_count_by_section || [],
    [detail.charts?.follow_up_count_by_section],
  );
  const followUpChapterOptions = useMemo(() => {
    const options = [
      {
        value: ALL_CHAPTER_FILTER_VALUE,
        label: t('module.dashboard.detail.charts.allChapters'),
      },
    ];
    const seenChapterBids = new Set<string>();
    followUpSections.forEach(section => {
      const chapterBid = section.chapter_outline_item_bid.trim();
      if (
        !chapterBid ||
        section.is_unassigned ||
        seenChapterBids.has(chapterBid)
      ) {
        return;
      }
      seenChapterBids.add(chapterBid);
      options.push({
        value: chapterBid,
        label:
          section.chapter_title ||
          t('module.dashboard.detail.charts.untitledChapter'),
      });
    });
    return options;
  }, [followUpSections, t]);

  useEffect(() => {
    if (
      selectedFollowUpChapter === ALL_CHAPTER_FILTER_VALUE ||
      followUpChapterOptions.some(
        option => option.value === selectedFollowUpChapter,
      )
    ) {
      return;
    }
    setSelectedFollowUpChapter(ALL_CHAPTER_FILTER_VALUE);
  }, [followUpChapterOptions, selectedFollowUpChapter]);

  const followUpSectionRows = useMemo(() => {
    const normalizeSectionTitle = (
      section: DashboardCourseDetailFollowUpCountBySection,
    ) => {
      if (section.is_unassigned) {
        return t('module.dashboard.detail.charts.unassignedSection');
      }
      return (
        section.section_title ||
        t('module.dashboard.detail.charts.untitledSection')
      );
    };

    const normalizedRows = followUpSections.map((section, index) => ({
      key: section.section_outline_item_bid || `section-${index}`,
      chapterTitle:
        section.chapter_title ||
        t('module.dashboard.detail.charts.untitledChapter'),
      sectionTitle: normalizeSectionTitle(section),
      label: normalizeSectionTitle(section),
      followUpCount: Number.isFinite(section.follow_up_count)
        ? section.follow_up_count
        : 0,
      isUnassigned: Boolean(section.is_unassigned),
      originalIndex: index,
    }));

    if (selectedFollowUpChapter !== ALL_CHAPTER_FILTER_VALUE) {
      return normalizedRows
        .filter(
          row =>
            !row.isUnassigned &&
            followUpSections[row.originalIndex]?.chapter_outline_item_bid ===
              selectedFollowUpChapter,
        )
        .map(({ originalIndex: _originalIndex, ...row }) => row);
    }

    if (normalizedRows.length <= FOLLOW_UP_SECTION_TOP_LIMIT) {
      return normalizedRows.map(
        ({ originalIndex: _originalIndex, ...row }) => row,
      );
    }

    const rankedRows = [...normalizedRows].sort((a, b) => {
      if (b.followUpCount !== a.followUpCount) {
        return b.followUpCount - a.followUpCount;
      }
      return a.originalIndex - b.originalIndex;
    });
    const topRows = rankedRows.slice(0, FOLLOW_UP_SECTION_TOP_LIMIT);
    const otherRows = rankedRows.slice(FOLLOW_UP_SECTION_TOP_LIMIT);
    const otherFollowUpCount = otherRows.reduce(
      (sum, row) => sum + row.followUpCount,
      0,
    );

    return [
      ...topRows.map(({ originalIndex: _originalIndex, ...row }) => row),
      {
        key: '__other__',
        chapterTitle: '',
        sectionTitle: t('module.dashboard.detail.charts.otherSections'),
        label: t('module.dashboard.detail.charts.otherSections'),
        followUpCount: otherFollowUpCount,
        isOther: true,
      },
    ];
  }, [followUpSections, selectedFollowUpChapter, t]);

  const followUpSectionChartOption = useMemo(
    () =>
      buildFollowUpSectionChartOption(
        followUpSectionRows,
        t('module.dashboard.detail.charts.followUpCountSeries'),
      ),
    [followUpSectionRows, t],
  );

  if (!isInitialized || isGuest || (loading && !detail.basic_info.shifu_bid)) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Loading />
      </div>
    );
  }

  if (error && !loading) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 500}
          errorMessage={error.message}
          onRetry={fetchDetail}
        />
      </div>
    );
  }

  return (
    <div className='h-full overflow-auto pr-1'>
      <div className='space-y-5 pb-6'>
        <div className='space-y-3'>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link href='/admin/dashboard'>
                    {t('module.dashboard.title')}
                  </Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>
                  {t('module.dashboard.detail.title')}
                </BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>

          <div className='space-y-1'>
            <h1 className='text-2xl font-semibold text-gray-900'>
              {t('module.dashboard.detail.title')}
            </h1>
            <div className='text-sm text-muted-foreground'>
              <span>{t('module.dashboard.detail.courseIdLabel')}</span>
              <span className='ml-1 font-medium text-foreground'>
                {detail.basic_info.shifu_bid || shifuBid || emptyValue}
              </span>
            </div>
            <p className='text-sm text-muted-foreground'>
              {t('module.dashboard.detail.subtitle')}
            </p>
          </div>
        </div>

        <Card>
          <CardContent className='p-5'>
            <div className='mb-4'>
              <h2 className='text-base font-semibold text-foreground'>
                {t('module.dashboard.detail.basicInfo.title')}
              </h2>
            </div>
            <dl className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
              <div className='space-y-1'>
                <dt className='text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.basicInfo.courseName')}
                </dt>
                <dd className='text-sm font-medium text-foreground'>
                  {detail.basic_info.course_name || emptyValue}
                </dd>
              </div>
              <div className='space-y-1'>
                <dt className='text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.basicInfo.createdAt')}
                </dt>
                <dd className='text-sm font-medium text-foreground'>
                  {formatDateTime(
                    detail.basic_info.created_at,
                    emptyValue,
                    detail.basic_info.created_at_display,
                  )}
                </dd>
              </div>
              <div className='space-y-1'>
                <dt className='text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.basicInfo.chapterCount')}
                </dt>
                <dd className='text-sm font-medium text-foreground'>
                  {formatCount(detail.basic_info.chapter_count, emptyValue)}
                </dd>
              </div>
              <div className='space-y-1'>
                <dt className='text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.basicInfo.learnerCount')}
                </dt>
                <dd className='text-sm font-medium text-foreground'>
                  {formatCount(detail.basic_info.learner_count, emptyValue)}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <div className='space-y-3'>
          <h2 className='text-base font-semibold text-foreground'>
            {t('module.dashboard.detail.metrics.title')}
          </h2>
          <div className='grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4'>
            {metricCards.map(metricCard => (
              <Card key={metricCard.label}>
                <CardContent className='p-4'>
                  <div className='text-sm text-muted-foreground'>
                    {metricCard.label}
                  </div>
                  {metricCard.onClick ? (
                    <button
                      type='button'
                      onClick={metricCard.onClick}
                      className='mt-3 text-left text-2xl font-semibold text-primary transition hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
                      aria-label={`${metricCard.label}-value`}
                    >
                      {metricCard.value}
                    </button>
                  ) : (
                    <div className='mt-3 text-2xl font-semibold text-foreground'>
                      {metricCard.value}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        <div className='space-y-3'>
          <h2 className='text-base font-semibold text-foreground'>
            {t('module.dashboard.detail.charts.title')}
          </h2>
          <div className='grid grid-cols-1 gap-4 xl:grid-cols-2'>
            <ChartCard
              className='xl:col-span-2'
              title={t('module.dashboard.detail.charts.questionsByChapter')}
              description={
                selectedFollowUpChapter === ALL_CHAPTER_FILTER_VALUE
                  ? t('module.dashboard.detail.charts.topSectionsDescription')
                  : t(
                      'module.dashboard.detail.charts.chapterSectionsDescription',
                    )
              }
              actions={
                <div className='flex items-center gap-2'>
                  <label
                    htmlFor='follow-up-section-chapter-filter'
                    className='text-xs font-medium text-muted-foreground'
                  >
                    {t('module.dashboard.detail.charts.chapterFilter')}
                  </label>
                  <select
                    id='follow-up-section-chapter-filter'
                    value={selectedFollowUpChapter}
                    onChange={event =>
                      setSelectedFollowUpChapter(event.target.value)
                    }
                    className='h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground shadow-sm focus:outline-none focus:ring-2 focus:ring-ring'
                  >
                    {followUpChapterOptions.map(option => (
                      <option
                        key={option.value}
                        value={option.value}
                      >
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              }
              contentClassName='min-h-[380px]'
            >
              {followUpSectionRows.length ? (
                <EChart
                  option={followUpSectionChartOption}
                  style={{ height: 360, width: '100%' }}
                  notMerge
                />
              ) : (
                <div className='flex h-[360px] items-center justify-center rounded-lg border border-dashed border-border bg-muted/30 text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.charts.emptyFollowUpSections')}
                </div>
              )}
            </ChartCard>

            {placeholderChartLabels.map((chartLabel, index) => (
              <Card
                key={chartLabel}
                className={index === 2 ? 'xl:col-span-2' : undefined}
              >
                <CardContent className='flex h-56 flex-col p-5'>
                  <div className='text-sm font-medium text-foreground'>
                    {chartLabel}
                  </div>
                  <div className='mt-4 flex flex-1 items-center justify-center rounded-lg border border-dashed border-border bg-muted/30 text-sm text-muted-foreground'>
                    {t('module.dashboard.detail.charts.placeholder')}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        <Card>
          <CardContent className='p-0'>
            <div className='border-b border-border px-5 py-4'>
              <h2 className='text-base font-semibold text-foreground'>
                {t('module.dashboard.detail.learners.title')}
              </h2>
            </div>
            <div className='p-5 pt-0'>
              <Table className='min-w-[720px]'>
                <TableHeader>
                  <TableRow>
                    {learnerTableColumnLabels.map(columnLabel => (
                      <TableHead key={columnLabel}>{columnLabel}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableEmpty colSpan={learnerTableColumnLabels.length}>
                    {t('module.dashboard.detail.learners.empty')}
                  </TableEmpty>
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
