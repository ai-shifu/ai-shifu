'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { TooltipProvider } from '@/components/ui/tooltip';
import { ErrorWithCode } from '@/lib/request';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { useUserStore } from '@/store';
import type {
  DashboardCourseDetailLearnerItem,
  DashboardCourseLearnersResponse,
  DashboardCourseDetailResponse,
} from '@/types/dashboard';
import {
  buildAdminDashboardCourseFollowUpsUrl,
  buildAdminDashboardCourseRatingsUrl,
  buildAdminOrdersUrl,
} from '../admin-dashboard-routes';
import { formatOrderAmount } from '../dashboardCourseTableRow';
import CourseMetricsCardGrid from '../../operations/[shifu_bid]/CourseMetricsCardGrid';
import DashboardCourseLearnersCard from './DashboardCourseLearnersCard';

type ErrorState = { message: string; code?: number };
type LearnerFilterStatus = 'all' | 'not_started' | 'learning' | 'completed';

const EMPTY_DETAIL: DashboardCourseDetailResponse = {
  basic_info: {
    shifu_bid: '',
    course_name: '',
    course_status: 'published',
    created_at: '',
    chapter_count: 0,
    learner_count: 0,
  },
  metrics: {
    order_count: 0,
    order_amount: '0.00',
    new_learner_count_last_7_days: 0,
    learning_learner_count: 0,
    completed_learner_count: 0,
    completion_rate: '0.00',
    active_learner_count_last_7_days: 0,
    total_follow_up_count: 0,
    rating_score: '',
  },
};

const EMPTY_LEARNERS: DashboardCourseLearnersResponse = {
  page: 1,
  page_count: 0,
  page_size: 20,
  total: 0,
  items: [],
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

export default function AdminDashboardCourseDetailPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams<{ shifu_bid?: string }>();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const currencySymbol = useEnvStore(state => state.currencySymbol || '¥');
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);
  const timezone = getBrowserTimeZone();

  const [detail, setDetail] =
    useState<DashboardCourseDetailResponse>(EMPTY_DETAIL);
  const [learners, setLearners] =
    useState<DashboardCourseLearnersResponse>(EMPTY_LEARNERS);
  const [detailLoading, setDetailLoading] = useState(false);
  const [learnersLoading, setLearnersLoading] = useState(false);
  const [detailError, setDetailError] = useState<ErrorState | null>(null);
  const [learnersError, setLearnersError] = useState<ErrorState | null>(null);
  const [learnerKeywordInput, setLearnerKeywordInput] = useState('');
  const [learnerKeyword, setLearnerKeyword] = useState('');
  const [learnerStatusInput, setLearnerStatusInput] =
    useState<LearnerFilterStatus>('all');
  const [learnerStatus, setLearnerStatus] =
    useState<LearnerFilterStatus>('all');
  const [learnerLastLearningStartInput, setLearnerLastLearningStartInput] =
    useState('');
  const [learnerLastLearningEndInput, setLearnerLastLearningEndInput] =
    useState('');
  const [learnerLastLearningStart, setLearnerLastLearningStart] = useState('');
  const [learnerLastLearningEnd, setLearnerLastLearningEnd] = useState('');
  const [learnerPage, setLearnerPage] = useState(1);
  const detailRequestIdRef = useRef(0);
  const learnersRequestIdRef = useRef(0);

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = '--';
  const orderListUrl = buildAdminOrdersUrl(shifuBid);
  const followUpListUrl = buildAdminDashboardCourseFollowUpsUrl(shifuBid);
  const ratingsPageUrl = buildAdminDashboardCourseRatingsUrl(shifuBid);
  const learnerSearchPlaceholder = useMemo(() => {
    const contactMode = resolveContactMode(
      loginMethodsEnabled,
      defaultLoginMethod,
    );
    return contactMode === 'email'
      ? t('module.dashboard.detail.learners.searchPlaceholderEmail')
      : t('module.dashboard.detail.learners.searchPlaceholderPhone');
  }, [defaultLoginMethod, loginMethodsEnabled, t]);
  const learnerContactMode = useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const courseStatusLabel = useMemo(() => {
    if (detail.basic_info.course_status === 'published') {
      return t('module.dashboard.detail.basicInfo.statusLabels.published');
    }
    if (detail.basic_info.course_status === 'unpublished') {
      return t('module.dashboard.detail.basicInfo.statusLabels.unpublished');
    }
    return detail.basic_info.course_status || emptyValue;
  }, [detail.basic_info.course_status, emptyValue, t]);

  const fetchDetail = useCallback(async () => {
    if (!shifuBid.trim()) {
      setDetail(EMPTY_DETAIL);
      setDetailError({ message: t('common.core.unknownError') });
      return;
    }

    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = (await api.getDashboardCourseDetail({
        shifu_bid: shifuBid,
        ...(timezone ? { timezone } : {}),
      })) as DashboardCourseDetailResponse;
      if (requestId !== detailRequestIdRef.current) {
        return;
      }
      setDetail(response || EMPTY_DETAIL);
    } catch (err) {
      if (requestId !== detailRequestIdRef.current) {
        return;
      }
      setDetail(EMPTY_DETAIL);
      if (err instanceof ErrorWithCode) {
        setDetailError({ message: err.message, code: err.code });
      } else if (err instanceof Error) {
        setDetailError({ message: err.message });
      } else {
        setDetailError({ message: t('common.core.unknownError') });
      }
    } finally {
      if (requestId === detailRequestIdRef.current) {
        setDetailLoading(false);
      }
    }
  }, [shifuBid, t, timezone]);

  const fetchLearners = useCallback(
    async (
      nextPage: number,
      nextFilters: {
        keyword: string;
        learningStatus: LearnerFilterStatus;
        lastLearningStart: string;
        lastLearningEnd: string;
      },
    ) => {
      if (!shifuBid.trim()) {
        setLearners(EMPTY_LEARNERS);
        setLearnersError({ message: t('common.core.unknownError') });
        return;
      }

      const requestId = learnersRequestIdRef.current + 1;
      learnersRequestIdRef.current = requestId;
      setLearnersLoading(true);
      setLearnersError(null);
      try {
        const response = (await api.getDashboardCourseLearners({
          shifu_bid: shifuBid,
          page_index: nextPage,
          page_size: 20,
          keyword: nextFilters.keyword,
          learning_status:
            nextFilters.learningStatus === 'all'
              ? ''
              : nextFilters.learningStatus,
          last_learning_start_time: nextFilters.lastLearningStart,
          last_learning_end_time: nextFilters.lastLearningEnd,
          ...(timezone ? { timezone } : {}),
        })) as DashboardCourseLearnersResponse;
        if (requestId !== learnersRequestIdRef.current) {
          return;
        }
        setLearners(response || EMPTY_LEARNERS);
      } catch (err) {
        if (requestId !== learnersRequestIdRef.current) {
          return;
        }
        setLearners(EMPTY_LEARNERS);
        if (err instanceof ErrorWithCode) {
          setLearnersError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setLearnersError({ message: err.message });
        } else {
          setLearnersError({ message: t('common.core.unknownError') });
        }
      } finally {
        if (requestId === learnersRequestIdRef.current) {
          setLearnersLoading(false);
        }
      }
    },
    [shifuBid, t, timezone],
  );

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

  useEffect(() => {
    if (!isInitialized || isGuest) {
      return;
    }
    fetchLearners(learnerPage, {
      keyword: learnerKeyword,
      learningStatus: learnerStatus,
      lastLearningStart: learnerLastLearningStart,
      lastLearningEnd: learnerLastLearningEnd,
    });
  }, [
    fetchLearners,
    isGuest,
    isInitialized,
    learnerKeyword,
    learnerLastLearningEnd,
    learnerLastLearningStart,
    learnerPage,
    learnerStatus,
  ]);

  const handleLearnerSearch = useCallback(() => {
    setLearnerPage(1);
    setLearnerKeyword(learnerKeywordInput.trim());
    setLearnerStatus(learnerStatusInput);
    setLearnerLastLearningStart(learnerLastLearningStartInput);
    setLearnerLastLearningEnd(learnerLastLearningEndInput);
  }, [
    learnerKeywordInput,
    learnerLastLearningEndInput,
    learnerLastLearningStartInput,
    learnerStatusInput,
  ]);

  const handleLearnerReset = useCallback(() => {
    setLearnerKeywordInput('');
    setLearnerKeyword('');
    setLearnerStatusInput('all');
    setLearnerStatus('all');
    setLearnerLastLearningStartInput('');
    setLearnerLastLearningEndInput('');
    setLearnerLastLearningStart('');
    setLearnerLastLearningEnd('');
    setLearnerPage(1);
  }, []);

  const handleLearnerPageChange = useCallback((nextPage: number) => {
    setLearnerPage(nextPage);
  }, []);

  const handleOrderClick = useCallback(() => {
    if (!orderListUrl) {
      return;
    }
    router.push(orderListUrl);
  }, [orderListUrl, router]);

  const handleFollowUpClick = useCallback(() => {
    if (!followUpListUrl) {
      return;
    }
    router.push(followUpListUrl);
  }, [followUpListUrl, router]);

  const handleRatingClick = useCallback(() => {
    if (!ratingsPageUrl) {
      return;
    }
    router.push(ratingsPageUrl);
  }, [ratingsPageUrl, router]);

  const handleLearnerFollowUpClick = useCallback(
    (learner: DashboardCourseDetailLearnerItem) => {
      const preferredKeyword =
        learnerContactMode === 'email'
          ? learner.email ||
            learner.mobile ||
            learner.nickname ||
            learner.user_bid
          : learner.mobile ||
            learner.email ||
            learner.nickname ||
            learner.user_bid;
      const targetUrl = buildAdminDashboardCourseFollowUpsUrl(shifuBid, {
        userBid: learner.user_bid,
        keyword: preferredKeyword,
      });
      if (!targetUrl) {
        return;
      }
      router.push(targetUrl);
    },
    [learnerContactMode, router, shifuBid],
  );

  const coreDataItems = useMemo(
    () => [
      {
        label: t('module.dashboard.detail.metrics.orderCount'),
        value: formatCount(detail.metrics.order_count, emptyValue),
        onClick: orderListUrl ? handleOrderClick : undefined,
        actionLabel: `${t('module.dashboard.detail.metrics.orderCount')}-value`,
      },
      {
        label: t('module.dashboard.detail.metrics.orderAmount'),
        value: formatOrderAmount(detail.metrics.order_amount, currencySymbol),
        onClick: orderListUrl ? handleOrderClick : undefined,
        actionLabel: `${t('module.dashboard.detail.metrics.orderAmount')}-value`,
      },
      {
        label: t('module.dashboard.detail.metrics.learningLearners'),
        value: formatCount(detail.metrics.learning_learner_count, emptyValue),
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
        label: t('module.dashboard.detail.metrics.newLearnersLast7Days'),
        value: formatCount(
          detail.metrics.new_learner_count_last_7_days,
          emptyValue,
        ),
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
        onClick: followUpListUrl ? handleFollowUpClick : undefined,
        actionLabel: `${t('module.dashboard.detail.metrics.totalQuestions')}-value`,
      },
      {
        label: t('module.dashboard.detail.metrics.rating'),
        value: detail.metrics.rating_score || emptyValue,
        onClick: ratingsPageUrl ? handleRatingClick : undefined,
        actionLabel: `${t('module.dashboard.detail.metrics.rating')}-value`,
      },
    ],
    [
      currencySymbol,
      detail.metrics.active_learner_count_last_7_days,
      detail.metrics.completed_learner_count,
      detail.metrics.completion_rate,
      detail.metrics.learning_learner_count,
      detail.metrics.new_learner_count_last_7_days,
      detail.metrics.order_amount,
      detail.metrics.order_count,
      detail.metrics.rating_score,
      detail.metrics.total_follow_up_count,
      emptyValue,
      followUpListUrl,
      handleFollowUpClick,
      handleOrderClick,
      handleRatingClick,
      orderListUrl,
      ratingsPageUrl,
      t,
    ],
  );

  const handleRetry = useCallback(() => {
    fetchDetail();
    fetchLearners(learnerPage, {
      keyword: learnerKeyword,
      learningStatus: learnerStatus,
      lastLearningStart: learnerLastLearningStart,
      lastLearningEnd: learnerLastLearningEnd,
    });
  }, [
    fetchDetail,
    fetchLearners,
    learnerKeyword,
    learnerLastLearningEnd,
    learnerLastLearningStart,
    learnerPage,
    learnerStatus,
  ]);

  if (
    !isInitialized ||
    isGuest ||
    (detailLoading && !detail.basic_info.shifu_bid)
  ) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Loading />
      </div>
    );
  }

  if (detailError && !detailLoading) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={detailError.code || 500}
          errorMessage={detailError.message}
          onRetry={handleRetry}
        />
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={150}>
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
          </div>

          <Card>
            <CardContent className='p-5'>
              <div className='mb-4'>
                <h2 className='text-base font-semibold text-foreground'>
                  {t('module.dashboard.detail.basicInfo.title')}
                </h2>
              </div>
              <dl className='grid gap-4 sm:grid-cols-2 xl:grid-cols-[1.65fr_1.2fr_0.9fr_0.75fr_0.75fr] xl:gap-5'>
                <div className='space-y-1'>
                  <dt className='min-h-[3.5rem] text-sm leading-7 text-muted-foreground'>
                    {t('module.dashboard.detail.courseIdLabel')}
                  </dt>
                  <dd className='text-sm font-medium text-foreground'>
                    <div className='whitespace-nowrap text-sm font-medium text-foreground'>
                      {detail.basic_info.shifu_bid || shifuBid || emptyValue}
                    </div>
                  </dd>
                </div>
                <div className='space-y-1'>
                  <dt className='min-h-[3.5rem] text-sm leading-7 text-muted-foreground'>
                    {t('module.dashboard.detail.basicInfo.courseName')}
                  </dt>
                  <dd className='text-sm font-medium text-foreground'>
                    <div className='break-all text-sm font-medium text-foreground'>
                      {detail.basic_info.course_name || emptyValue}
                    </div>
                  </dd>
                </div>
                <div className='space-y-1 xl:pl-4'>
                  <dt className='min-h-[3.5rem] text-sm leading-7 text-muted-foreground'>
                    {t('module.dashboard.detail.basicInfo.status')}
                  </dt>
                  <dd className='text-sm font-medium text-foreground'>
                    {courseStatusLabel}
                  </dd>
                </div>
                <div className='space-y-1 xl:pl-4'>
                  <dt className='min-h-[3.5rem] text-sm leading-7 text-muted-foreground'>
                    {t('module.dashboard.detail.basicInfo.learnerCount')}
                  </dt>
                  <dd className='text-sm font-medium text-foreground'>
                    {formatCount(detail.basic_info.learner_count, emptyValue)}
                  </dd>
                </div>
                <div className='space-y-1 xl:pl-4'>
                  <dt className='min-h-[3.5rem] text-sm leading-7 text-muted-foreground'>
                    {t('module.dashboard.detail.basicInfo.chapterCount')}
                  </dt>
                  <dd className='text-sm font-medium text-foreground'>
                    {formatCount(detail.basic_info.chapter_count, emptyValue)}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <CourseMetricsCardGrid
            title={t('module.dashboard.detail.metrics.title')}
            cards={coreDataItems}
          />

          <DashboardCourseLearnersCard
            learners={learners}
            loading={learnersLoading}
            error={learnersError}
            keyword={learnerKeywordInput}
            learningStatus={learnerStatusInput}
            lastLearningStart={learnerLastLearningStartInput}
            lastLearningEnd={learnerLastLearningEndInput}
            searchPlaceholder={learnerSearchPlaceholder}
            emptyValue={emptyValue}
            onKeywordChange={setLearnerKeywordInput}
            onLearningStatusChange={value => setLearnerStatusInput(value)}
            onLastLearningTimeChange={({ start, end }) => {
              setLearnerLastLearningStartInput(start);
              setLearnerLastLearningEndInput(end);
            }}
            onSearch={handleLearnerSearch}
            onReset={handleLearnerReset}
            onPageChange={handleLearnerPageChange}
            onFollowUpClick={handleLearnerFollowUpClick}
          />
        </div>
      </div>
    </TooltipProvider>
  );
}
