'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import { formatAdminNaiveDateTime } from '@/app/admin/lib/dateTime';
import { formatAdminCount } from '@/app/admin/lib/numberFormat';
import { useEnvStore } from '@/c-store';
import { copyText } from '@/c-utils/textutils';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { fail, show } from '@/hooks/useToast';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import {
  buildAdminOperationsCourseFollowUpsUrl,
  buildAdminOperationsOrdersUrl,
  buildAdminOperationsCourseRatingsUrl,
} from '../operation-course-routes';
import type {
  AdminOperationCourseCreditUsageFilters,
  AdminOperationCourseCreditUsageListResponse,
  AdminOperationCourseChapterDetailResponse,
  AdminOperationCourseDetailChapter,
  AdminOperationCourseDetailResponse,
  AdminOperationCourseUserItem,
  AdminOperationCourseUsersResponse,
} from '../operation-course-types';
import CourseChapterDetailDialog from './CourseChapterDetailDialog';
import CourseChaptersTab, {
  type FlattenedChapterRow,
} from './CourseChaptersTab';
import CourseBasicInfoCard from './CourseBasicInfoCard';
import CourseCreditUsageTab from './CourseCreditUsageTab';
import CourseMetricsCardGrid from './CourseMetricsCardGrid';
import CourseUsersTab from './CourseUsersTab';
import {
  createCourseUserFilters,
  type CourseUserFilters,
  USER_COLUMN_DEFAULT_WIDTHS,
  USER_COLUMN_KEYS,
  USER_COLUMN_MAX_WIDTH,
  USER_COLUMN_MIN_WIDTH,
  USER_COLUMN_WIDTH_STORAGE_KEY,
  type UserColumnKey,
} from './courseUsersTabConfig';
import useOperatorGuard from '../useOperatorGuard';

type ErrorState = { message: string; code?: number };

type CourseDetailTab = 'chapters' | 'users' | 'creditUsage';

const EMPTY_CHAPTER_DETAIL: AdminOperationCourseChapterDetailResponse = {
  outline_item_bid: '',
  title: '',
  content: '',
  llm_system_prompt: '',
  llm_system_prompt_source: '',
};

const CHAPTER_COLUMN_MIN_WIDTH = 80;
const CHAPTER_COLUMN_MAX_WIDTH = 420;
const CHAPTER_COLUMN_WIDTH_STORAGE_KEY =
  'adminOperationCourseDetailColumnWidths';
const CHAPTER_COLUMN_DEFAULT_WIDTHS = {
  position: 90,
  name: 220,
  learningPermission: 130,
  visibility: 110,
  contentStatus: 110,
  modifier: 170,
  updatedAt: 170,
  contentDetail: 100,
  followUpCount: 100,
  ratingScore: 90,
  ratingCount: 100,
} as const;

type ChapterColumnKey = keyof typeof CHAPTER_COLUMN_DEFAULT_WIDTHS;
const CHAPTER_COLUMN_KEYS = Object.keys(
  CHAPTER_COLUMN_DEFAULT_WIDTHS,
) as ChapterColumnKey[];
const USER_PAGE_SIZE = 20;
const COURSE_CREDIT_USAGE_PAGE_SIZE = 20;
const FILTER_ALL_OPTION = 'all';

const EMPTY_COURSE_USERS_RESPONSE: AdminOperationCourseUsersResponse = {
  items: [],
  page: 1,
  page_count: 0,
  page_size: USER_PAGE_SIZE,
  total: 0,
};

const EMPTY_COURSE_CREDIT_USAGE_RESPONSE: AdminOperationCourseCreditUsageListResponse =
  {
    view: 'grouped',
    items: [],
    page: 1,
    page_count: 0,
    page_size: COURSE_CREDIT_USAGE_PAGE_SIZE,
    total: 0,
  };

const EMPTY_DETAIL: AdminOperationCourseDetailResponse = {
  basic_info: {
    shifu_bid: '',
    course_name: '',
    course_status: 'unpublished',
    creator_user_bid: '',
    creator_mobile: '',
    creator_email: '',
    creator_nickname: '',
    created_at: '',
    updated_at: '',
  },
  metrics: {
    visit_count_30d: 0,
    learner_count: 0,
    order_count: 0,
    order_amount: '0',
    follow_up_count: 0,
    rating_score: '',
  },
  chapters: [],
};

const flattenChapters = (
  chapters: AdminOperationCourseDetailChapter[],
  depth = 0,
): FlattenedChapterRow[] =>
  chapters.flatMap(chapter => [
    { ...chapter, depth },
    ...flattenChapters(chapter.children || [], depth + 1),
  ]);

const formatCount = (value: number, locale: string): string =>
  formatAdminCount(value, locale);

const formatLearningProgress = (
  learnedLessonCount: number,
  totalLessonCount: number,
  locale: string,
): string =>
  `${formatCount(learnedLessonCount, locale)} / ${formatCount(
    totalLessonCount,
    locale,
  )}`;

const createCourseCreditUsageFilters =
  (): AdminOperationCourseCreditUsageFilters => ({
    keyword: '',
    mode: FILTER_ALL_OPTION,
    startTime: '',
    endTime: '',
  });

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.operationsCourse.detail.title')
 * t('module.operationsCourse.detail.back')
 * t('module.operationsCourse.detail.basicInfo')
 * t('module.operationsCourse.detail.metrics')
 * t('module.operationsCourse.detail.chapters')
 * t('module.operationsCourse.detail.fields.courseName')
 * t('module.operationsCourse.detail.fields.courseId')
 * t('module.operationsCourse.detail.fields.status')
 * t('module.operationsCourse.detail.fields.creator')
 * t('module.operationsCourse.detail.fields.createdAt')
 * t('module.operationsCourse.detail.fields.updatedAt')
 * t('module.operationsCourse.detail.metricsLabels.visitCount30d')
 * t('module.operationsCourse.detail.metricsLabels.learnerCount')
 * t('module.operationsCourse.detail.metricsLabels.orderCount')
 * t('module.operationsCourse.detail.metricsLabels.orderAmount')
 * t('module.operationsCourse.detail.metricsLabels.followUpCount')
 * t('module.operationsCourse.detail.metricsLabels.ratingScore')
 * t('module.operationsCourse.detail.orders.openMetric')
 * t('module.operationsCourse.detail.followUps.openMetric')
 * t('module.operationsCourse.detail.ratings.openMetric')
 * t('module.operationsCourse.detail.chaptersTable.position')
 * t('module.operationsCourse.detail.chaptersTable.name')
 * t('module.operationsCourse.detail.chaptersTable.type')
 * t('module.operationsCourse.detail.chaptersTable.learningPermission')
 * t('module.operationsCourse.detail.chaptersTable.visibility')
 * t('module.operationsCourse.detail.chaptersTable.contentStatus')
 * t('module.operationsCourse.detail.chaptersTable.modifier')
 * t('module.operationsCourse.detail.chaptersTable.contentDetail')
 * t('module.operationsCourse.detail.chaptersTable.followUpCount')
 * t('module.operationsCourse.detail.chaptersTable.ratingScore')
 * t('module.operationsCourse.detail.chaptersTable.ratingCount')
 * t('module.operationsCourse.detail.chaptersTable.updatedAt')
 * t('module.operationsCourse.detail.chaptersTable.empty')
 * t('module.operationsCourse.detail.chaptersTable.detailAction')
 * t('module.operationsCourse.detail.chapterType.chapter')
 * t('module.operationsCourse.detail.chapterType.lesson')
 * t('module.operationsCourse.detail.learningPermission.guest')
 * t('module.operationsCourse.detail.learningPermission.free')
 * t('module.operationsCourse.detail.learningPermission.paid')
 * t('module.operationsCourse.detail.learningPermission.unknown')
 * t('module.operationsCourse.detail.visibility.visible')
 * t('module.operationsCourse.detail.visibility.hidden')
 * t('module.operationsCourse.detail.contentStatus.has')
 * t('module.operationsCourse.detail.contentStatus.empty')
 * t('module.operationsCourse.detail.contentStatus.unknown')
 * t('module.operationsCourse.detail.contentDetailDialog.title')
 * t('module.operationsCourse.detail.contentDetailDialog.copy')
 * t('module.operationsCourse.detail.contentDetailDialog.copySuccess')
 * t('module.operationsCourse.detail.contentDetailDialog.copyFailed')
 * t('module.operationsCourse.detail.contentDetailDialog.empty')
 * t('module.operationsCourse.detail.contentDetailDialog.sections.content')
 * t('module.operationsCourse.detail.contentDetailDialog.sections.systemPrompt')
 * t('module.operationsCourse.detail.contentDetailDialog.sources.lesson')
 * t('module.operationsCourse.detail.contentDetailDialog.sources.chapter')
 * t('module.operationsCourse.detail.contentDetailDialog.sources.course')
 * t('module.operationsCourse.detail.users')
 * t('module.operationsCourse.detail.usersCount')
 * t('module.operationsCourse.detail.usersDescription')
 * t('module.operationsCourse.detail.usersFilters.userKeyword')
 * t('module.operationsCourse.detail.usersFilters.userKeywordPlaceholder')
 * t('module.operationsCourse.detail.usersFilters.userKeywordPlaceholderPhone')
 * t('module.operationsCourse.detail.usersFilters.userKeywordPlaceholderEmail')
 * t('module.operationsCourse.detail.usersFilters.userRole')
 * t('module.operationsCourse.detail.usersFilters.learningStatus')
 * t('module.operationsCourse.detail.usersFilters.paymentStatus')
 * t('module.operationsCourse.detail.usersFilters.all')
 * t('module.operationsCourse.detail.usersFilters.paymentPaid')
 * t('module.operationsCourse.detail.usersFilters.paymentUnpaid')
 * t('module.operationsCourse.detail.usersTable.account')
 * t('module.operationsCourse.detail.usersTable.accountPhone')
 * t('module.operationsCourse.detail.usersTable.accountEmail')
 * t('module.operationsCourse.detail.usersTable.nickname')
 * t('module.operationsCourse.detail.usersTable.userRole')
 * t('module.operationsCourse.detail.usersTable.learningProgress')
 * t('module.operationsCourse.detail.usersTable.learningStatus')
 * t('module.operationsCourse.detail.usersTable.isPaid')
 * t('module.operationsCourse.detail.usersTable.totalPaidAmount')
 * t('module.operationsCourse.detail.usersTable.lastLearnedAt')
 * t('module.operationsCourse.detail.usersTable.joinedAt')
 * t('module.operationsCourse.detail.usersTable.lastLoginAt')
 * t('module.operationsCourse.detail.usersTable.action')
 * t('module.operationsCourse.detail.usersTable.empty')
 * t('module.operationsCourse.detail.usersTable.detailAction')
 * t('module.operationsCourse.detail.creditUsageTab')
 * t('module.operationsCourse.detail.creditUsage.title')
 * t('module.operationsCourse.detail.creditUsage.description')
 * t('module.operationsCourse.detail.creditUsage.count')
 * t('module.operationsCourse.detail.creditUsage.filters.userKeyword')
 * t('module.operationsCourse.detail.creditUsage.filters.userKeywordPlaceholderPhone')
 * t('module.operationsCourse.detail.creditUsage.filters.userKeywordPlaceholderEmail')
 * t('module.operationsCourse.detail.creditUsage.filters.mode')
 * t('module.operationsCourse.detail.creditUsage.filters.modeAll')
 * t('module.operationsCourse.detail.creditUsage.filters.time')
 * t('module.operationsCourse.detail.creditUsage.filters.timePlaceholder')
 * t('module.operationsCourse.detail.creditUsage.filters.reset')
 * t('module.operationsCourse.detail.creditUsage.modes.learn')
 * t('module.operationsCourse.detail.creditUsage.modes.listen')
 * t('module.operationsCourse.detail.creditUsage.modes.ask')
 * t('module.operationsCourse.detail.creditUsage.modes.mixed')
 * t('module.operationsCourse.detail.creditUsage.modes.unknown')
 * t('module.operationsCourse.detail.creditUsage.modelSummary.multiple')
 * t('module.operationsCourse.detail.creditUsage.table.createdAt')
 * t('module.operationsCourse.detail.creditUsage.table.nickname')
 * t('module.operationsCourse.detail.creditUsage.table.mode')
 * t('module.operationsCourse.detail.creditUsage.table.chapter')
 * t('module.operationsCourse.detail.creditUsage.table.lesson')
 * t('module.operationsCourse.detail.creditUsage.table.usageCount')
 * t('module.operationsCourse.detail.creditUsage.table.credits')
 * t('module.operationsCourse.detail.creditUsage.table.model')
 * t('module.operationsCourse.detail.creditUsage.table.empty')
 * t('module.operationsCourse.detail.userRole.operator')
 * t('module.operationsCourse.detail.userRole.creator')
 * t('module.operationsCourse.detail.userRole.student')
 * t('module.operationsCourse.detail.userRole.normal')
 * t('module.operationsCourse.detail.userLearningStatus.notStarted')
 * t('module.operationsCourse.detail.userLearningStatus.learning')
 * t('module.operationsCourse.detail.userLearningStatus.completed')
 * t('module.operationsCourse.detail.boolean.yes')
 * t('module.operationsCourse.detail.boolean.no')
 * t('module.operationsCourse.statusLabels.unknown')
 */
export default function AdminOperationCourseDetailPage() {
  const router = useRouter();
  const params = useParams<{ shifu_bid?: string }>();
  const { t, i18n } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');
  const { isReady } = useOperatorGuard();
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);
  const currencySymbol = useEnvStore(state => state.currencySymbol || '');

  const [detail, setDetail] =
    useState<AdminOperationCourseDetailResponse>(EMPTY_DETAIL);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [activeTab, setActiveTab] = useState<CourseDetailTab>('chapters');
  const [selectedChapter, setSelectedChapter] =
    useState<FlattenedChapterRow | null>(null);
  const [selectedChapterDetail, setSelectedChapterDetail] =
    useState<AdminOperationCourseChapterDetailResponse>(EMPTY_CHAPTER_DETAIL);
  const [chapterDetailLoading, setChapterDetailLoading] = useState(false);
  const [courseUserFiltersDraft, setCourseUserFiltersDraft] =
    useState<CourseUserFilters>(createCourseUserFilters);
  const [courseUserFilters, setCourseUserFilters] = useState<CourseUserFilters>(
    createCourseUserFilters,
  );
  const [courseUsers, setCourseUsers] =
    useState<AdminOperationCourseUsersResponse>(EMPTY_COURSE_USERS_RESPONSE);
  const [courseUsersLoading, setCourseUsersLoading] = useState(false);
  const [courseUsersError, setCourseUsersError] = useState<ErrorState | null>(
    null,
  );
  const [courseUserPage, setCourseUserPage] = useState(1);
  const courseUsersRequestIdRef = useRef(0);
  const [courseCreditUsageFiltersDraft, setCourseCreditUsageFiltersDraft] =
    useState<AdminOperationCourseCreditUsageFilters>(
      createCourseCreditUsageFilters,
    );
  const [courseCreditUsageFilters, setCourseCreditUsageFilters] =
    useState<AdminOperationCourseCreditUsageFilters>(
      createCourseCreditUsageFilters,
    );
  const [courseCreditUsages, setCourseCreditUsages] =
    useState<AdminOperationCourseCreditUsageListResponse>(
      EMPTY_COURSE_CREDIT_USAGE_RESPONSE,
    );
  const [courseCreditUsagesLoading, setCourseCreditUsagesLoading] =
    useState(false);
  const [courseCreditUsagesError, setCourseCreditUsagesError] =
    useState<ErrorState | null>(null);
  const [courseCreditUsagePage, setCourseCreditUsagePage] = useState(1);
  const courseCreditUsagesRequestIdRef = useRef(0);
  const {
    setColumnWidths: setChapterColumnWidths,
    getColumnStyle: getChapterColumnStyle,
    getResizeHandleProps: getChapterResizeHandleProps,
    isManualColumn: isManualChapterColumn,
    clampWidth: clampChapterWidth,
  } = useAdminResizableColumns<ChapterColumnKey>({
    storageKey: CHAPTER_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: CHAPTER_COLUMN_DEFAULT_WIDTHS,
    minWidth: CHAPTER_COLUMN_MIN_WIDTH,
    maxWidth: CHAPTER_COLUMN_MAX_WIDTH,
  });
  const {
    setColumnWidths: setUserColumnWidths,
    getColumnStyle: getUserColumnStyle,
    getResizeHandleProps: getUserResizeHandleProps,
    isManualColumn: isManualUserColumn,
    clampWidth: clampUserWidth,
  } = useAdminResizableColumns<UserColumnKey>({
    storageKey: USER_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: USER_COLUMN_DEFAULT_WIDTHS,
    minWidth: USER_COLUMN_MIN_WIDTH,
    maxWidth: USER_COLUMN_MAX_WIDTH,
  });
  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const followUpPageUrl = useMemo(
    () => buildAdminOperationsCourseFollowUpsUrl(shifuBid),
    [shifuBid],
  );
  const ratingsPageUrl = useMemo(
    () => buildAdminOperationsCourseRatingsUrl(shifuBid),
    [shifuBid],
  );
  const ordersPageUrl = useMemo(
    () => buildAdminOperationsOrdersUrl(shifuBid),
    [shifuBid],
  );
  const emptyValue = '--';
  const unknownErrorMessage = t('common.core.unknownError');
  const contactMode = useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const defaultUserName = useMemo(() => t('module.user.defaultUserName'), [t]);
  const courseUserKeywordPlaceholder = useMemo(
    () =>
      contactMode === 'email'
        ? tOperations('detail.usersFilters.userKeywordPlaceholderEmail')
        : tOperations('detail.usersFilters.userKeywordPlaceholderPhone'),
    [contactMode, tOperations],
  );
  const courseUserAccountLabel = useMemo(
    () =>
      contactMode === 'email'
        ? tOperations('detail.usersTable.accountEmail')
        : tOperations('detail.usersTable.accountPhone'),
    [contactMode, tOperations],
  );
  const fetchDetail = useCallback(async () => {
    if (!shifuBid.trim()) {
      setError({ message: unknownErrorMessage });
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = (await api.getAdminOperationCourseDetail({
        shifu_bid: shifuBid,
      })) as AdminOperationCourseDetailResponse;
      setDetail(response || EMPTY_DETAIL);
    } catch (err) {
      setDetail(EMPTY_DETAIL);
      if (err instanceof ErrorWithCode) {
        setError({ message: err.message, code: err.code });
      } else if (err instanceof Error) {
        setError({ message: err.message });
      } else {
        setError({ message: unknownErrorMessage });
      }
    } finally {
      setLoading(false);
    }
  }, [shifuBid, unknownErrorMessage]);

  const fetchCourseUsers = useCallback(
    async (targetPage: number, nextFilters?: CourseUserFilters) => {
      if (!shifuBid.trim()) {
        setCourseUsersError({ message: unknownErrorMessage });
        setCourseUsers(EMPTY_COURSE_USERS_RESPONSE);
        return;
      }

      const resolvedFilters = nextFilters ?? courseUserFilters;
      const requestId = courseUsersRequestIdRef.current + 1;
      courseUsersRequestIdRef.current = requestId;
      setCourseUsersLoading(true);
      setCourseUsersError(null);

      try {
        const response = (await api.getAdminOperationCourseUsers({
          shifu_bid: shifuBid,
          page: targetPage,
          page_size: USER_PAGE_SIZE,
          keyword: resolvedFilters.keyword.trim(),
          user_role: resolvedFilters.userRole,
          learning_status: resolvedFilters.learningStatus,
          payment_status: resolvedFilters.paymentStatus,
        })) as AdminOperationCourseUsersResponse;
        if (requestId !== courseUsersRequestIdRef.current) {
          return;
        }
        setCourseUsers({
          items: response?.items || [],
          page: response?.page || targetPage,
          page_count: response?.page_count || 0,
          page_size: response?.page_size || USER_PAGE_SIZE,
          total: response?.total || 0,
        });
      } catch (err) {
        if (requestId !== courseUsersRequestIdRef.current) {
          return;
        }
        setCourseUsers(EMPTY_COURSE_USERS_RESPONSE);
        if (err instanceof ErrorWithCode) {
          setCourseUsersError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setCourseUsersError({ message: err.message });
        } else {
          setCourseUsersError({ message: unknownErrorMessage });
        }
      } finally {
        if (requestId === courseUsersRequestIdRef.current) {
          setCourseUsersLoading(false);
        }
      }
    },
    [courseUserFilters, shifuBid, unknownErrorMessage],
  );

  const fetchCourseCreditUsages = useCallback(
    async (
      targetPage: number,
      nextFilters?: AdminOperationCourseCreditUsageFilters,
    ) => {
      if (!shifuBid.trim()) {
        setCourseCreditUsagesError({ message: unknownErrorMessage });
        setCourseCreditUsages(EMPTY_COURSE_CREDIT_USAGE_RESPONSE);
        return;
      }

      const resolvedFilters = nextFilters ?? courseCreditUsageFilters;
      const requestId = courseCreditUsagesRequestIdRef.current + 1;
      courseCreditUsagesRequestIdRef.current = requestId;
      setCourseCreditUsagesLoading(true);
      setCourseCreditUsagesError(null);

      try {
        const response = (await api.getAdminOperationCourseCreditUsages({
          shifu_bid: shifuBid,
          page: targetPage,
          page_size: COURSE_CREDIT_USAGE_PAGE_SIZE,
          view: 'grouped',
          keyword: resolvedFilters.keyword.trim(),
          mode:
            resolvedFilters.mode === FILTER_ALL_OPTION
              ? ''
              : resolvedFilters.mode,
          start_time: resolvedFilters.startTime,
          end_time: resolvedFilters.endTime,
        })) as AdminOperationCourseCreditUsageListResponse;
        if (requestId !== courseCreditUsagesRequestIdRef.current) {
          return;
        }
        setCourseCreditUsages({
          view: response?.view || 'grouped',
          items: response?.items || [],
          page: response?.page || targetPage,
          page_count: response?.page_count || 0,
          page_size: response?.page_size || COURSE_CREDIT_USAGE_PAGE_SIZE,
          total: response?.total || 0,
        });
      } catch (err) {
        if (requestId !== courseCreditUsagesRequestIdRef.current) {
          return;
        }
        setCourseCreditUsages(EMPTY_COURSE_CREDIT_USAGE_RESPONSE);
        if (err instanceof ErrorWithCode) {
          setCourseCreditUsagesError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setCourseCreditUsagesError({ message: err.message });
        } else {
          setCourseCreditUsagesError({ message: unknownErrorMessage });
        }
      } finally {
        if (requestId === courseCreditUsagesRequestIdRef.current) {
          setCourseCreditUsagesLoading(false);
        }
      }
    },
    [courseCreditUsageFilters, shifuBid, unknownErrorMessage],
  );

  useEffect(() => {
    if (!isReady) {
      return;
    }
    fetchDetail();
  }, [fetchDetail, isReady]);

  useEffect(() => {
    if (!isReady || activeTab !== 'users') {
      return;
    }
    fetchCourseUsers(courseUserPage, courseUserFilters);
  }, [activeTab, courseUserFilters, courseUserPage, fetchCourseUsers, isReady]);

  useEffect(() => {
    if (!isReady || activeTab !== 'creditUsage') {
      return;
    }
    fetchCourseCreditUsages(courseCreditUsagePage, courseCreditUsageFilters);
  }, [
    activeTab,
    courseCreditUsageFilters,
    courseCreditUsagePage,
    fetchCourseCreditUsages,
    isReady,
  ]);

  const formatUnknownEnumLabel = useCallback(
    (labelKey: string, rawValue?: string) => {
      const fallbackLabel = tOperations(labelKey);
      const normalizedValue = (rawValue || '').trim();
      if (!normalizedValue) {
        return fallbackLabel;
      }

      const wrapper = /[^\x00-\x7F]/.test(`${fallbackLabel}${normalizedValue}`)
        ? ['（', '）']
        : [' (', ')'];
      return `${fallbackLabel}${wrapper[0]}${normalizedValue}${wrapper[1]}`;
    },
    [tOperations],
  );

  const resolveCourseStatusLabel = useCallback(
    (courseStatus?: string) => {
      if (courseStatus === 'published') {
        return tOperations('statusLabels.published');
      }
      if (courseStatus === 'unpublished') {
        return tOperations('statusLabels.unpublished');
      }
      return formatUnknownEnumLabel('statusLabels.unknown', courseStatus);
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveLearningPermissionLabel = useCallback(
    (permission?: string) => {
      if (permission === 'guest') {
        return tOperations('detail.learningPermission.guest');
      }
      if (permission === 'free') {
        return tOperations('detail.learningPermission.free');
      }
      if (permission === 'paid') {
        return tOperations('detail.learningPermission.paid');
      }
      return formatUnknownEnumLabel(
        'detail.learningPermission.unknown',
        permission,
      );
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveContentStatusLabel = useCallback(
    (contentStatus?: string) => {
      if (contentStatus === 'has') {
        return tOperations('detail.contentStatus.has');
      }
      if (contentStatus === 'empty') {
        return tOperations('detail.contentStatus.empty');
      }
      return formatUnknownEnumLabel(
        'detail.contentStatus.unknown',
        contentStatus,
      );
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveChapterTypeLabel = useCallback(
    (nodeType?: string) => {
      if (nodeType === 'chapter') {
        return tOperations('detail.chapterType.chapter');
      }
      if (nodeType === 'lesson') {
        return tOperations('detail.chapterType.lesson');
      }
      return formatUnknownEnumLabel('statusLabels.unknown', nodeType);
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveModifierDisplay = useCallback(
    (chapter: AdminOperationCourseDetailChapter) => {
      const primary =
        chapter.modifier_mobile ||
        chapter.modifier_email ||
        chapter.modifier_user_bid ||
        emptyValue;
      const secondary =
        chapter.modifier_nickname &&
        chapter.modifier_nickname !== t('module.user.defaultUserName')
          ? chapter.modifier_nickname
          : '';
      return {
        primary,
        secondary,
      };
    },
    [emptyValue, t],
  );

  const creatorDisplay = useMemo(() => {
    const primary =
      detail.basic_info.creator_mobile ||
      detail.basic_info.creator_email ||
      detail.basic_info.creator_user_bid ||
      emptyValue;
    const secondary = detail.basic_info.creator_nickname || '';
    return {
      primary,
      secondary:
        secondary && secondary !== t('module.user.defaultUserName')
          ? secondary
          : '',
    };
  }, [
    detail.basic_info.creator_email,
    detail.basic_info.creator_mobile,
    detail.basic_info.creator_nickname,
    detail.basic_info.creator_user_bid,
    emptyValue,
    t,
  ]);

  const metricCards = useMemo(
    () => [
      {
        label: tOperations('detail.metricsLabels.visitCount30d'),
        value: formatCount(detail.metrics.visit_count_30d, i18n.language),
      },
      {
        label: tOperations('detail.metricsLabels.learnerCount'),
        value: formatCount(detail.metrics.learner_count, i18n.language),
      },
      {
        label: tOperations('detail.metricsLabels.orderCount'),
        value: formatCount(detail.metrics.order_count, i18n.language),
        onClick: ordersPageUrl ? () => router.push(ordersPageUrl) : undefined,
        actionLabel: tOperations('detail.orders.openMetric'),
      },
      {
        label: tOperations('detail.metricsLabels.orderAmount'),
        value: `${currencySymbol}${detail.metrics.order_amount || '0'}`,
      },
      {
        label: tOperations('detail.metricsLabels.followUpCount'),
        value: formatCount(detail.metrics.follow_up_count, i18n.language),
        onClick: followUpPageUrl
          ? () => router.push(followUpPageUrl)
          : undefined,
        actionLabel: tOperations('detail.followUps.openMetric'),
      },
      {
        label: tOperations('detail.metricsLabels.ratingScore'),
        value: detail.metrics.rating_score || emptyValue,
        onClick: ratingsPageUrl ? () => router.push(ratingsPageUrl) : undefined,
        actionLabel: tOperations('detail.ratings.openMetric'),
      },
    ],
    [
      currencySymbol,
      detail.metrics,
      emptyValue,
      followUpPageUrl,
      i18n.language,
      ordersPageUrl,
      ratingsPageUrl,
      router,
      tOperations,
    ],
  );

  const resolveCourseUserRoleLabel = useCallback(
    (userRole: AdminOperationCourseUserItem['user_role']) => {
      if (userRole === 'operator') {
        return tOperations('detail.userRole.operator');
      }
      if (userRole === 'creator') {
        return tOperations('detail.userRole.creator');
      }
      if (userRole === 'student') {
        return tOperations('detail.userRole.student');
      }
      if (userRole === 'normal') {
        return tOperations('detail.userRole.normal');
      }
      return formatUnknownEnumLabel('statusLabels.unknown', userRole);
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveCourseUserLearningStatusLabel = useCallback(
    (learningStatus: AdminOperationCourseUserItem['learning_status']) => {
      if (learningStatus === 'completed') {
        return tOperations('detail.userLearningStatus.completed');
      }
      if (learningStatus === 'learning') {
        return tOperations('detail.userLearningStatus.learning');
      }
      if (learningStatus === 'not_started') {
        return tOperations('detail.userLearningStatus.notStarted');
      }
      return formatUnknownEnumLabel('statusLabels.unknown', learningStatus);
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveCourseUserPaidAmountDisplay = useCallback(
    (courseUser: AdminOperationCourseUserItem) =>
      String(courseUser.total_paid_amount || '0'),
    [],
  );

  const currentCourseUserPage = courseUsers.page || 1;
  const courseUserPageCount = Math.max(courseUsers.page_count || 0, 1);
  const courseUserRows = useMemo(
    () => courseUsers.items || [],
    [courseUsers.items],
  );

  const resolveCourseUserAccount = useCallback(
    (courseUser: AdminOperationCourseUserItem) => {
      const preferred =
        contactMode === 'email' ? courseUser.email : courseUser.mobile;
      return preferred || emptyValue;
    },
    [contactMode, emptyValue],
  );

  const handleCourseUserSearch = useCallback(() => {
    const nextFilters = {
      ...courseUserFiltersDraft,
      keyword: courseUserFiltersDraft.keyword.trim(),
    };
    setCourseUserFilters(nextFilters);
    setCourseUserPage(1);
  }, [courseUserFiltersDraft]);

  const applyCourseUserSelectFilter = useCallback(
    (partialFilters: Partial<CourseUserFilters>) => {
      const nextDraftFilters = {
        ...courseUserFiltersDraft,
        ...partialFilters,
      };
      const nextFilters = {
        ...courseUserFilters,
        ...partialFilters,
        keyword: courseUserFilters.keyword.trim(),
      };
      setCourseUserFiltersDraft(nextDraftFilters);
      setCourseUserFilters(nextFilters);
      setCourseUserPage(1);
    },
    [courseUserFilters, courseUserFiltersDraft],
  );

  const handleCourseUserReset = useCallback(() => {
    const nextFilters = createCourseUserFilters();
    setCourseUserFiltersDraft(nextFilters);
    setCourseUserFilters(nextFilters);
    setCourseUserPage(1);
  }, []);

  const handleCourseUserPageChange = useCallback(
    (nextPage: number) => {
      if (
        nextPage < 1 ||
        nextPage > courseUserPageCount ||
        nextPage === currentCourseUserPage
      ) {
        return;
      }
      setCourseUserPage(nextPage);
    },
    [courseUserPageCount, currentCourseUserPage],
  );

  const handleCourseCreditUsageSearch = useCallback(() => {
    const nextFilters = {
      ...courseCreditUsageFiltersDraft,
      keyword: courseCreditUsageFiltersDraft.keyword.trim(),
    };
    setCourseCreditUsageFilters(nextFilters);
    setCourseCreditUsagePage(1);
  }, [courseCreditUsageFiltersDraft]);

  const handleCourseCreditUsageReset = useCallback(() => {
    const nextFilters = createCourseCreditUsageFilters();
    setCourseCreditUsageFiltersDraft(nextFilters);
    setCourseCreditUsageFilters(nextFilters);
    setCourseCreditUsagePage(1);
  }, []);

  const handleCourseCreditUsagePageChange = useCallback(
    (nextPage: number) => {
      const currentPage = courseCreditUsages.page || 1;
      const pageCount = Math.max(courseCreditUsages.page_count || 0, 1);
      if (nextPage < 1 || nextPage > pageCount || nextPage === currentPage) {
        return;
      }
      setCourseCreditUsagePage(nextPage);
    },
    [courseCreditUsages.page, courseCreditUsages.page_count],
  );

  const chapterRows = useMemo(
    () => flattenChapters(detail.chapters || []),
    [detail.chapters],
  );

  const resolvePromptSourceLabel = useCallback(
    (source?: string) => {
      if (source === 'lesson') {
        return tOperations('detail.contentDetailDialog.sources.lesson');
      }
      if (source === 'chapter') {
        return tOperations('detail.contentDetailDialog.sources.chapter');
      }
      if (source === 'course') {
        return tOperations('detail.contentDetailDialog.sources.course');
      }
      return '';
    },
    [tOperations],
  );

  const buildPromptSectionLabel = useCallback(
    (baseLabel: string, source?: string) => {
      const sourceLabel = resolvePromptSourceLabel(source);
      if (!sourceLabel) {
        return baseLabel;
      }
      const wrapper = /[^\x00-\x7F]/.test(`${baseLabel}${sourceLabel}`)
        ? ['（', '）']
        : [' (', ')'];
      return `${baseLabel}${wrapper[0]}${sourceLabel}${wrapper[1]}`;
    },
    [resolvePromptSourceLabel],
  );

  const selectedChapterDetailSections = useMemo(() => {
    if (!selectedChapter) {
      return [];
    }
    return [
      {
        label: tOperations('detail.contentDetailDialog.sections.content'),
        value: selectedChapterDetail.content || '',
      },
      {
        label: buildPromptSectionLabel(
          tOperations('detail.contentDetailDialog.sections.systemPrompt'),
          selectedChapterDetail.llm_system_prompt_source,
        ),
        value: selectedChapterDetail.llm_system_prompt || '',
      },
    ];
  }, [
    buildPromptSectionLabel,
    selectedChapter,
    selectedChapterDetail,
    tOperations,
  ]);

  const selectedChapterCopyText = useMemo(() => {
    const sections = selectedChapterDetailSections.filter(section =>
      section.value.trim(),
    );
    if (sections.length === 0) {
      return '';
    }
    return sections
      .map(section => `${section.label}\n${section.value}`)
      .join('\n\n');
  }, [selectedChapterDetailSections]);

  const handleCopyChapterDetail = useCallback(async () => {
    if (!selectedChapterCopyText) {
      return;
    }
    try {
      await copyText(selectedChapterCopyText);
      show(tOperations('detail.contentDetailDialog.copySuccess'));
    } catch {
      fail(tOperations('detail.contentDetailDialog.copyFailed'));
    }
  }, [selectedChapterCopyText, tOperations]);

  const chapterDetailLayout = useMemo(() => {
    const populatedSections = selectedChapterDetailSections.filter(section =>
      section.value.trim(),
    );
    const totalCharacters = populatedSections.reduce(
      (sum, section) => sum + section.value.trim().length,
      0,
    );

    if (chapterDetailLoading) {
      return {
        dialogClassName: 'w-[min(88vw,760px)] max-w-[760px] p-0',
        bodyClassName: 'min-h-[260px] max-h-[420px] overflow-auto px-6 py-5',
      };
    }

    if (!populatedSections.length) {
      return {
        dialogClassName: 'w-[min(84vw,640px)] max-w-[640px] p-0',
        bodyClassName: 'min-h-[220px] max-h-[320px] overflow-auto px-6 py-5',
      };
    }

    if (totalCharacters <= 600) {
      return {
        dialogClassName: 'w-[min(88vw,760px)] max-w-[760px] p-0',
        bodyClassName: 'min-h-[240px] max-h-[460px] overflow-auto px-6 py-5',
      };
    }

    return {
      dialogClassName: 'w-[min(92vw,980px)] max-w-5xl p-0',
      bodyClassName: 'h-[70vh] max-h-[720px] overflow-auto px-6 py-5',
    };
  }, [chapterDetailLoading, selectedChapterDetailSections]);

  useEffect(() => {
    if (!selectedChapter?.outline_item_bid) {
      setSelectedChapterDetail(EMPTY_CHAPTER_DETAIL);
      setChapterDetailLoading(false);
      return;
    }

    let isActive = true;
    setChapterDetailLoading(true);
    setSelectedChapterDetail(EMPTY_CHAPTER_DETAIL);

    api
      .getAdminOperationCourseChapterDetail({
        shifu_bid: shifuBid,
        outline_item_bid: selectedChapter.outline_item_bid,
      })
      .then(response => {
        if (!isActive) {
          return;
        }
        setSelectedChapterDetail(
          (response as AdminOperationCourseChapterDetailResponse) ||
            EMPTY_CHAPTER_DETAIL,
        );
      })
      .catch(err => {
        if (!isActive) {
          return;
        }
        const message =
          err instanceof ErrorWithCode || err instanceof Error
            ? err.message
            : t('common.core.unknownError');
        fail(message);
        setSelectedChapter(null);
      })
      .finally(() => {
        if (isActive) {
          setChapterDetailLoading(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [selectedChapter?.outline_item_bid, shifuBid, t]);

  const estimateChapterColumnWidth = useCallback(
    (text: string, multiplier = 7) => {
      if (!text) {
        return CHAPTER_COLUMN_MIN_WIDTH;
      }
      return text.length * multiplier + 24;
    },
    [],
  );

  const estimateUserColumnWidth = useCallback(
    (text: string, multiplier = 7) => {
      if (!text) {
        return USER_COLUMN_MIN_WIDTH;
      }
      return text.length * multiplier + 24;
    },
    [],
  );

  const autoAdjustChapterColumns = useCallback(
    (rows: FlattenedChapterRow[]) => {
      if (!rows.length) {
        setChapterColumnWidths(prev => {
          const next = { ...prev };
          CHAPTER_COLUMN_KEYS.forEach(key => {
            if (!isManualChapterColumn(key)) {
              next[key] = CHAPTER_COLUMN_DEFAULT_WIDTHS[key];
            }
          });
          return next;
        });
        return;
      }

      const nextWidths: Partial<Record<ChapterColumnKey, number>> = {};
      const columnValueExtractors: Record<
        ChapterColumnKey,
        (chapter: FlattenedChapterRow) => string[]
      > = {
        position: chapter => [chapter.position],
        name: chapter => [
          chapter.title,
          chapter.node_type,
          ' '.repeat(chapter.depth),
        ],
        learningPermission: chapter => [
          resolveLearningPermissionLabel(chapter.learning_permission),
        ],
        visibility: chapter => [
          chapter.is_visible
            ? tOperations('detail.visibility.visible')
            : tOperations('detail.visibility.hidden'),
        ],
        contentStatus: chapter => [
          resolveContentStatusLabel(chapter.content_status),
        ],
        modifier: chapter => {
          const modifier = resolveModifierDisplay(chapter);
          return [modifier.primary, modifier.secondary];
        },
        contentDetail: () => [tOperations('detail.chaptersTable.detailAction')],
        followUpCount: chapter => [
          chapter.node_type === 'chapter'
            ? emptyValue
            : formatCount(chapter.follow_up_count, i18n.language),
        ],
        ratingScore: chapter => [
          chapter.node_type === 'chapter'
            ? emptyValue
            : chapter.rating_score || emptyValue,
        ],
        ratingCount: chapter => [
          chapter.node_type === 'chapter'
            ? emptyValue
            : formatCount(chapter.rating_count, i18n.language),
        ],
        updatedAt: chapter => [chapter.updated_at],
      };

      const multiplierMap: Partial<Record<ChapterColumnKey, number>> = {
        position: 5,
        name: 8,
        learningPermission: 6,
        visibility: 6,
        contentStatus: 6,
        modifier: 5.2,
        contentDetail: 5,
        followUpCount: 5,
        ratingScore: 5,
        ratingCount: 5,
        updatedAt: 5,
      };

      rows.forEach(chapter => {
        CHAPTER_COLUMN_KEYS.forEach(key => {
          const texts = columnValueExtractors[key](chapter).filter(Boolean);
          if (!texts.length) {
            return;
          }
          const required = texts.reduce(
            (maxWidth, text) =>
              Math.max(
                maxWidth,
                estimateChapterColumnWidth(text, multiplierMap[key] ?? 7),
              ),
            Number(CHAPTER_COLUMN_DEFAULT_WIDTHS[key]),
          );
          if (
            !nextWidths[key] ||
            required > (nextWidths[key] ?? CHAPTER_COLUMN_MIN_WIDTH)
          ) {
            nextWidths[key] = required;
          }
        });
      });

      setChapterColumnWidths(prev => {
        const next = { ...prev };
        CHAPTER_COLUMN_KEYS.forEach(key => {
          if (!isManualChapterColumn(key)) {
            next[key] = clampChapterWidth(
              nextWidths[key] ?? CHAPTER_COLUMN_DEFAULT_WIDTHS[key],
            );
          }
        });
        return next;
      });
    },
    [
      clampChapterWidth,
      estimateChapterColumnWidth,
      i18n.language,
      isManualChapterColumn,
      resolveContentStatusLabel,
      resolveLearningPermissionLabel,
      resolveModifierDisplay,
      setChapterColumnWidths,
      tOperations,
    ],
  );

  const autoAdjustUserColumns = useCallback(
    (rows: AdminOperationCourseUserItem[]) => {
      if (!rows.length) {
        setUserColumnWidths(prev => {
          const next = { ...prev };
          USER_COLUMN_KEYS.forEach(key => {
            if (!isManualUserColumn(key)) {
              next[key] = USER_COLUMN_DEFAULT_WIDTHS[key];
            }
          });
          return next;
        });
        return;
      }

      const nextWidths: Partial<Record<UserColumnKey, number>> = {};
      const columnValueExtractors: Record<
        UserColumnKey,
        (user: AdminOperationCourseUserItem) => string[]
      > = {
        account: user => [resolveCourseUserAccount(user)],
        nickname: user => [user.nickname || defaultUserName],
        userRole: user => [resolveCourseUserRoleLabel(user.user_role)],
        learningProgress: user => [
          formatLearningProgress(
            user.learned_lesson_count,
            user.total_lesson_count,
            i18n.language,
          ),
        ],
        learningStatus: user => [
          resolveCourseUserLearningStatusLabel(user.learning_status),
        ],
        isPaid: user => [
          user.is_paid
            ? tOperations('detail.boolean.yes')
            : tOperations('detail.boolean.no'),
        ],
        totalPaidAmount: user => [resolveCourseUserPaidAmountDisplay(user)],
        lastLearnedAt: user => [user.last_learning_at || emptyValue],
        joinedAt: user => [user.joined_at || emptyValue],
        lastLoginAt: user => [user.last_login_at || emptyValue],
        action: () => [emptyValue],
      };

      const multiplierMap: Partial<Record<UserColumnKey, number>> = {
        account: 6,
        nickname: 6,
        userRole: 5.5,
        learningProgress: 5.5,
        learningStatus: 5.5,
        isPaid: 5,
        totalPaidAmount: 5.5,
        lastLearnedAt: 5,
        lastLoginAt: 5,
        joinedAt: 5,
        action: 5,
      };

      rows.forEach(user => {
        USER_COLUMN_KEYS.forEach(key => {
          const texts = columnValueExtractors[key](user).filter(Boolean);
          if (!texts.length) {
            return;
          }
          const required = texts.reduce(
            (maxWidth, text) =>
              Math.max(
                maxWidth,
                estimateUserColumnWidth(text, multiplierMap[key] ?? 7),
              ),
            Number(USER_COLUMN_DEFAULT_WIDTHS[key]),
          );
          if (
            !nextWidths[key] ||
            required > (nextWidths[key] ?? USER_COLUMN_MIN_WIDTH)
          ) {
            nextWidths[key] = required;
          }
        });
      });

      setUserColumnWidths(prev => {
        const next = { ...prev };
        USER_COLUMN_KEYS.forEach(key => {
          if (!isManualUserColumn(key)) {
            next[key] = clampUserWidth(
              nextWidths[key] ?? USER_COLUMN_DEFAULT_WIDTHS[key],
            );
          }
        });
        return next;
      });
    },
    [
      clampUserWidth,
      defaultUserName,
      emptyValue,
      estimateUserColumnWidth,
      i18n.language,
      isManualUserColumn,
      resolveCourseUserAccount,
      resolveCourseUserLearningStatusLabel,
      resolveCourseUserPaidAmountDisplay,
      resolveCourseUserRoleLabel,
      setUserColumnWidths,
      tOperations,
    ],
  );

  const basicInfoItems = useMemo(
    () => [
      {
        label: tOperations('detail.fields.courseName'),
        value: detail.basic_info.course_name || emptyValue,
      },
      {
        label: tOperations('detail.fields.courseId'),
        value: detail.basic_info.shifu_bid || shifuBid || emptyValue,
      },
      {
        label: tOperations('detail.fields.status'),
        value: (
          <span className='font-medium text-foreground'>
            {resolveCourseStatusLabel(detail.basic_info.course_status)}
          </span>
        ),
      },
      {
        label: tOperations('detail.fields.creator'),
        value: (
          <div className='space-y-0.5'>
            <div className='font-medium text-foreground'>
              {creatorDisplay.primary}
            </div>
            {creatorDisplay.secondary ? (
              <div className='text-xs text-muted-foreground'>
                {creatorDisplay.secondary}
              </div>
            ) : null}
          </div>
        ),
      },
      {
        label: tOperations('detail.fields.createdAt'),
        value:
          formatAdminNaiveDateTime(detail.basic_info.created_at) || emptyValue,
      },
      {
        label: tOperations('detail.fields.updatedAt'),
        value:
          formatAdminNaiveDateTime(detail.basic_info.updated_at) || emptyValue,
      },
    ],
    [
      creatorDisplay.primary,
      creatorDisplay.secondary,
      detail.basic_info.course_name,
      detail.basic_info.course_status,
      detail.basic_info.created_at,
      detail.basic_info.shifu_bid,
      detail.basic_info.updated_at,
      emptyValue,
      resolveCourseStatusLabel,
      shifuBid,
      tOperations,
    ],
  );

  useEffect(() => {
    autoAdjustChapterColumns(chapterRows);
  }, [autoAdjustChapterColumns, chapterRows]);

  useEffect(() => {
    autoAdjustUserColumns(courseUserRows);
  }, [autoAdjustUserColumns, courseUserRows]);

  if (!isReady) {
    return <Loading />;
  }

  if (loading && !detail.basic_info.shifu_bid) {
    return <Loading />;
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
    <div className='h-full min-h-0 overflow-hidden bg-stone-50 p-0 overscroll-none'>
      <div className='mx-auto flex h-full min-h-0 w-full max-w-7xl flex-col overflow-hidden'>
        <div className='mb-5 flex shrink-0 flex-col gap-3 pt-6 sm:flex-row sm:items-start sm:justify-between'>
          <h1 className='text-2xl font-semibold text-gray-900'>
            {tOperations('detail.title')}
          </h1>
          <Button
            variant='outline'
            className='sm:mr-3'
            onClick={() => router.push('/admin/operations')}
          >
            {tOperations('detail.back')}
          </Button>
        </div>

        <div className='min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain pr-1'>
          <div className='space-y-5 pb-6'>
            <CourseBasicInfoCard
              title={tOperations('detail.basicInfo')}
              items={basicInfoItems}
            />

            <CourseMetricsCardGrid
              title={tOperations('detail.metrics')}
              cards={metricCards}
            />

            <Tabs
              value={activeTab}
              onValueChange={value => setActiveTab(value as CourseDetailTab)}
              className='space-y-4'
            >
              <div className='overflow-x-auto'>
                <TabsList>
                  <TabsTrigger value='chapters'>
                    {tOperations('detail.chapters')}
                  </TabsTrigger>
                  <TabsTrigger value='users'>
                    {tOperations('detail.users')}
                  </TabsTrigger>
                  <TabsTrigger value='creditUsage'>
                    {tOperations('detail.creditUsageTab')}
                  </TabsTrigger>
                </TabsList>
              </div>

              <TabsContent
                value='chapters'
                className='mt-0'
              >
                <CourseChaptersTab
                  rows={chapterRows}
                  emptyValue={emptyValue}
                  locale={i18n.language}
                  onOpenChapterDetail={setSelectedChapter}
                  resolveChapterTypeLabel={resolveChapterTypeLabel}
                  resolveLearningPermissionLabel={
                    resolveLearningPermissionLabel
                  }
                  resolveContentStatusLabel={resolveContentStatusLabel}
                  resolveModifierDisplay={resolveModifierDisplay}
                  formatCount={formatCount}
                  formatAdminNaiveDateTime={formatAdminNaiveDateTime}
                  getColumnStyle={getChapterColumnStyle}
                  getResizeHandleProps={getChapterResizeHandleProps}
                  tOperations={tOperations}
                />
              </TabsContent>

              <TabsContent
                value='users'
                className='mt-0'
              >
                <CourseUsersTab
                  filtersDraft={courseUserFiltersDraft}
                  loading={courseUsersLoading}
                  error={courseUsersError}
                  users={courseUsers}
                  rows={courseUserRows}
                  pageIndex={currentCourseUserPage}
                  pageCount={courseUserPageCount}
                  contactKeywordPlaceholder={courseUserKeywordPlaceholder}
                  accountLabel={courseUserAccountLabel}
                  emptyValue={emptyValue}
                  defaultUserName={defaultUserName}
                  locale={i18n.language}
                  onKeywordChange={value =>
                    setCourseUserFiltersDraft(prev => ({
                      ...prev,
                      keyword: value,
                    }))
                  }
                  onUserRoleChange={value =>
                    applyCourseUserSelectFilter({ userRole: value })
                  }
                  onLearningStatusChange={value =>
                    applyCourseUserSelectFilter({ learningStatus: value })
                  }
                  onPaymentStatusChange={value =>
                    applyCourseUserSelectFilter({
                      paymentStatus: value,
                    })
                  }
                  onSearch={handleCourseUserSearch}
                  onReset={handleCourseUserReset}
                  onPageChange={handleCourseUserPageChange}
                  resolveCourseUserRoleLabel={resolveCourseUserRoleLabel}
                  resolveCourseUserLearningStatusLabel={
                    resolveCourseUserLearningStatusLabel
                  }
                  resolveCourseUserPaidAmountDisplay={
                    resolveCourseUserPaidAmountDisplay
                  }
                  resolveCourseUserAccount={resolveCourseUserAccount}
                  formatLearningProgress={formatLearningProgress}
                  getColumnStyle={getUserColumnStyle}
                  getResizeHandleProps={getUserResizeHandleProps}
                />
              </TabsContent>

              <TabsContent
                value='creditUsage'
                className='mt-0'
              >
                <CourseCreditUsageTab
                  filtersDraft={courseCreditUsageFiltersDraft}
                  data={courseCreditUsages}
                  loading={courseCreditUsagesLoading}
                  error={courseCreditUsagesError}
                  contactMode={contactMode}
                  defaultUserName={defaultUserName}
                  emptyValue={emptyValue}
                  onKeywordChange={value =>
                    setCourseCreditUsageFiltersDraft(prev => ({
                      ...prev,
                      keyword: value,
                    }))
                  }
                  onModeChange={value =>
                    setCourseCreditUsageFiltersDraft(prev => ({
                      ...prev,
                      mode: value,
                    }))
                  }
                  onDateRangeChange={({ start, end }) =>
                    setCourseCreditUsageFiltersDraft(prev => ({
                      ...prev,
                      startTime: start,
                      endTime: end,
                    }))
                  }
                  onSearch={handleCourseCreditUsageSearch}
                  onReset={handleCourseCreditUsageReset}
                  onPageChange={handleCourseCreditUsagePageChange}
                />
              </TabsContent>
            </Tabs>
          </div>
        </div>

        <CourseChapterDetailDialog
          open={Boolean(selectedChapter)}
          selectedChapter={selectedChapter}
          loading={chapterDetailLoading}
          copyDisabled={!selectedChapterCopyText}
          layout={chapterDetailLayout}
          sections={selectedChapterDetailSections}
          onOpenChange={open => {
            if (!open) {
              setSelectedChapter(null);
              setSelectedChapterDetail(EMPTY_CHAPTER_DETAIL);
            }
          }}
          onCopy={handleCopyChapterDetail}
          tOperations={tOperations}
        />
      </div>
    </div>
  );
}
