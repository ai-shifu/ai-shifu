'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useEnvStore } from '@/c-store';
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
import ChartCard from '@/components/charts/ChartCard';
import EChart from '@/components/charts/EChart';
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
import { buildSectionLearningChartOption } from '@/lib/dashboard/section-learning-chart';
import type { SectionChartLabels } from '@/lib/dashboard/section-learning-chart';
import { useUserStore } from '@/store';
import type { DashboardCourseDetailResponse } from '@/types/dashboard';
import { buildAdminOrdersUrl } from '../admin-dashboard-routes';
import { formatOrderAmount } from '../dashboardCourseTableRow';

type ErrorState = { message: string; code?: number };

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
    sections: [],
  },
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

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = '--';
  const orderListUrl = buildAdminOrdersUrl(shifuBid);

  const sectionChartLabels = useMemo<SectionChartLabels>(
    () => ({
      learningUserCount: t('module.dashboard.detail.charts.learningUserCount'),
      learningRecordCount: t(
        'module.dashboard.detail.charts.learningRecordCount',
      ),
      followUpUserCount: t('module.dashboard.detail.charts.followUpUserCount'),
      followUpQuestionCount: t(
        'module.dashboard.detail.charts.followUpQuestionCount',
      ),
    }),
    [t],
  );

  const sectionChartOption = useMemo(
    () =>
      buildSectionLearningChartOption(
        detail.charts.sections || [],
        sectionChartLabels,
      ),
    [detail.charts.sections, sectionChartLabels],
  );

  const sectionChartHasData = (detail.charts.sections || []).length > 0;
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
      })) as Partial<DashboardCourseDetailResponse> | null;
      setDetail({
        ...EMPTY_DETAIL,
        ...(response ?? {}),
        basic_info: { ...EMPTY_DETAIL.basic_info, ...(response?.basic_info ?? {}) },
        metrics: { ...EMPTY_DETAIL.metrics, ...(response?.metrics ?? {}) },
        charts: { sections: response?.charts?.sections ?? [] },
      });
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
          <ChartCard
            title={t('module.dashboard.detail.charts.sectionLearningTitle')}
            contentClassName='min-h-[380px]'
          >
            {sectionChartHasData ? (
              <EChart
                option={sectionChartOption}
                style={{ height: 360, width: '100%' }}
                notMerge
              />
            ) : (
              <div className='flex h-[360px] items-center justify-center rounded-lg border border-dashed border-border bg-muted/30 text-sm text-muted-foreground'>
                {t('module.dashboard.detail.charts.emptySections')}
              </div>
            )}
          </ChartCard>
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
