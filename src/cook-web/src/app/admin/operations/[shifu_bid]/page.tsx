'use client';

import { Copy, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTimezoneHint from '@/app/admin/components/AdminTimezoneHint';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import { useEnvStore } from '@/c-store';
import { copyText } from '@/c-utils/textutils';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Label } from '@/components/ui/Label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { fail, show } from '@/hooks/useToast';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { cn } from '@/lib/utils';
import {
  buildAdminOperationsCourseFollowUpsUrl,
  buildAdminOperationsOrdersUrl,
} from '../operation-course-routes';
import type {
  AdminOperationCourseChapterDetailResponse,
  AdminOperationCourseDetailChapter,
  AdminOperationCourseDetailResponse,
  AdminOperationCourseUserItem,
  AdminOperationCourseUsersResponse,
} from '../operation-course-types';
import useOperatorGuard from '../useOperatorGuard';

type ErrorState = { message: string; code?: number };

type FlattenedChapterRow = AdminOperationCourseDetailChapter & {
  depth: number;
};

type CourseUserPaymentStatus = 'all' | 'paid' | 'unpaid';
type CourseUserFilters = {
  keyword: string;
  userRole: string;
  learningStatus: string;
  paymentStatus: CourseUserPaymentStatus;
};
type CourseDetailTab = 'chapters' | 'users';

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
const USER_COLUMN_MIN_WIDTH = 80;
const USER_COLUMN_MAX_WIDTH = 320;
const USER_COLUMN_WIDTH_STORAGE_KEY = 'adminOperationCourseUserColumnWidths';
const USER_COLUMN_DEFAULT_WIDTHS = {
  account: 170,
  nickname: 140,
  userRole: 120,
  learningProgress: 120,
  learningStatus: 120,
  isPaid: 90,
  totalPaidAmount: 120,
  lastLearnedAt: 170,
  lastLoginAt: 170,
  joinedAt: 170,
  action: 90,
} as const;

type UserColumnKey = keyof typeof USER_COLUMN_DEFAULT_WIDTHS;
const USER_COLUMN_KEYS = Object.keys(
  USER_COLUMN_DEFAULT_WIDTHS,
) as UserColumnKey[];
const USER_PAGE_SIZE = 20;
const FILTER_ALL_OPTION = 'all';

const EMPTY_COURSE_USERS_RESPONSE: AdminOperationCourseUsersResponse = {
  items: [],
  page: 1,
  page_count: 0,
  page_size: USER_PAGE_SIZE,
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

const formatCount = (value: number): string =>
  Number.isFinite(value) ? value.toLocaleString() : '--';

const formatLearningProgress = (
  learnedLessonCount: number,
  totalLessonCount: number,
): string =>
  `${formatCount(learnedLessonCount)} / ${formatCount(totalLessonCount)}`;

const createCourseUserFilters = (): CourseUserFilters => ({
  keyword: '',
  userRole: FILTER_ALL_OPTION,
  learningStatus: FILTER_ALL_OPTION,
  paymentStatus: FILTER_ALL_OPTION,
});

function ClearableTextInput({
  value,
  placeholder,
  clearLabel,
  onChange,
}: {
  value: string;
  placeholder: string;
  clearLabel: string;
  onChange: (value: string) => void;
}) {
  const hasValue = value.trim().length > 0;

  return (
    <div className='flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-within:outline-none'>
      <input
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className='h-full min-w-0 flex-1 border-0 bg-transparent p-0 text-sm leading-none text-foreground placeholder:text-muted-foreground focus:outline-none'
      />
      {hasValue ? (
        <button
          type='button'
          aria-label={clearLabel}
          className='ml-2 shrink-0 rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground'
          onMouseDown={event => event.preventDefault()}
          onClick={() => onChange('')}
        >
          <X className='h-3.5 w-3.5' />
        </button>
      ) : null}
    </div>
  );
}

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
  const { t } = useTranslation();
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
        value: formatCount(detail.metrics.visit_count_30d),
      },
      {
        label: tOperations('detail.metricsLabels.learnerCount'),
        value: formatCount(detail.metrics.learner_count),
      },
      {
        label: tOperations('detail.metricsLabels.orderCount'),
        value: formatCount(detail.metrics.order_count),
        onClick: ordersPageUrl ? () => router.push(ordersPageUrl) : undefined,
        actionLabel: tOperations('detail.orders.openMetric'),
      },
      {
        label: tOperations('detail.metricsLabels.orderAmount'),
        value: `${currencySymbol}${detail.metrics.order_amount || '0'}`,
      },
      {
        label: tOperations('detail.metricsLabels.followUpCount'),
        value: formatCount(detail.metrics.follow_up_count),
        onClick: followUpPageUrl
          ? () => router.push(followUpPageUrl)
          : undefined,
        actionLabel: tOperations('detail.followUps.openMetric'),
      },
      {
        label: tOperations('detail.metricsLabels.ratingScore'),
        value: detail.metrics.rating_score || emptyValue,
      },
    ],
    [
      currencySymbol,
      detail.metrics,
      emptyValue,
      followUpPageUrl,
      ordersPageUrl,
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
            : formatCount(chapter.follow_up_count),
        ],
        ratingScore: chapter => [
          chapter.node_type === 'chapter'
            ? emptyValue
            : chapter.rating_score || emptyValue,
        ],
        ratingCount: chapter => [
          chapter.node_type === 'chapter'
            ? emptyValue
            : formatCount(chapter.rating_count),
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
      isManualUserColumn,
      resolveCourseUserAccount,
      resolveCourseUserLearningStatusLabel,
      resolveCourseUserPaidAmountDisplay,
      resolveCourseUserRoleLabel,
      setUserColumnWidths,
      tOperations,
    ],
  );

  const renderChapterResizeHandle = (key: ChapterColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getChapterResizeHandleProps(key)}
    />
  );

  const renderUserResizeHandle = (key: UserColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getUserResizeHandleProps(key)}
    />
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
          formatAdminUtcDateTime(detail.basic_info.created_at) || emptyValue,
      },
      {
        label: tOperations('detail.fields.updatedAt'),
        value:
          formatAdminUtcDateTime(detail.basic_info.updated_at) || emptyValue,
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
          <div className='space-y-1'>
            <h1 className='text-2xl font-semibold text-gray-900'>
              {tOperations('detail.title')}
            </h1>
            <AdminTimezoneHint
              namespace='module.operationsCourse'
              textKey='timezoneHint'
            />
          </div>
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
            <Card>
              <CardHeader className='pb-4'>
                <CardTitle className='text-base font-semibold tracking-normal'>
                  {tOperations('detail.basicInfo')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <dl className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>
                  {basicInfoItems.map(item => (
                    <div
                      key={item.label}
                      className='space-y-1'
                    >
                      <dt className='text-sm text-muted-foreground'>
                        {item.label}
                      </dt>
                      <dd className='text-sm text-foreground'>{item.value}</dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className='pb-4'>
                <CardTitle className='text-base font-semibold tracking-normal'>
                  {tOperations('detail.metrics')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-5'>
                  {metricCards.map(card => {
                    const cardContent = (
                      <>
                        <div className='text-sm font-medium text-muted-foreground'>
                          {card.label}
                        </div>
                        <div className='mt-3 flex items-end gap-1.5'>
                          <span
                            className={cn(
                              'text-2xl font-semibold',
                              card.onClick ? 'text-primary' : 'text-foreground',
                            )}
                          >
                            {card.value}
                          </span>
                        </div>
                      </>
                    );

                    if (card.onClick) {
                      return (
                        <button
                          key={card.label}
                          type='button'
                          aria-label={card.actionLabel || card.label}
                          className='rounded-lg border border-border/70 bg-muted/20 p-4 text-left transition-colors hover:border-primary/30 hover:bg-primary/[0.04]'
                          onClick={card.onClick}
                        >
                          {cardContent}
                        </button>
                      );
                    }

                    return (
                      <div
                        key={card.label}
                        className='rounded-lg border border-border/70 bg-muted/20 p-4 text-left'
                      >
                        {cardContent}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

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
                </TabsList>
              </div>

              <TabsContent
                value='chapters'
                className='mt-0'
              >
                <Card>
                  <CardHeader className='pb-4'>
                    <CardTitle className='text-base font-semibold tracking-normal'>
                      {tOperations('detail.chapters')}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className='pt-0'>
                    <AdminTableShell
                      loading={false}
                      isEmpty={chapterRows.length === 0}
                      emptyContent={tOperations('detail.chaptersTable.empty')}
                      emptyColSpan={11}
                      withTooltipProvider
                      tableWrapperClassName='overflow-auto'
                      table={emptyRow => (
                        <Table className='table-auto'>
                          <TableHeader>
                            <TableRow>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('position')}
                              >
                                {tOperations('detail.chaptersTable.position')}
                                {renderChapterResizeHandle('position')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('name')}
                              >
                                {tOperations('detail.chaptersTable.name')}
                                {renderChapterResizeHandle('name')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle(
                                  'learningPermission',
                                )}
                              >
                                {tOperations(
                                  'detail.chaptersTable.learningPermission',
                                )}
                                {renderChapterResizeHandle(
                                  'learningPermission',
                                )}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('visibility')}
                              >
                                {tOperations('detail.chaptersTable.visibility')}
                                {renderChapterResizeHandle('visibility')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('contentStatus')}
                              >
                                {tOperations(
                                  'detail.chaptersTable.contentStatus',
                                )}
                                {renderChapterResizeHandle('contentStatus')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('contentDetail')}
                              >
                                {tOperations(
                                  'detail.chaptersTable.contentDetail',
                                )}
                                {renderChapterResizeHandle('contentDetail')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('modifier')}
                              >
                                {tOperations('detail.chaptersTable.modifier')}
                                {renderChapterResizeHandle('modifier')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('updatedAt')}
                              >
                                {tOperations('detail.chaptersTable.updatedAt')}
                                {renderChapterResizeHandle('updatedAt')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap border-l-2 border-l-border/80 bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('followUpCount')}
                              >
                                {tOperations(
                                  'detail.chaptersTable.followUpCount',
                                )}
                                {renderChapterResizeHandle('followUpCount')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('ratingScore')}
                              >
                                {tOperations(
                                  'detail.chaptersTable.ratingScore',
                                )}
                                {renderChapterResizeHandle('ratingScore')}
                              </TableHead>
                              <TableHead
                                className={cn(
                                  ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
                                  'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                )}
                                style={getChapterColumnStyle('ratingCount')}
                              >
                                {tOperations(
                                  'detail.chaptersTable.ratingCount',
                                )}
                                {renderChapterResizeHandle('ratingCount')}
                              </TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {emptyRow}
                            {chapterRows.map(chapter => {
                              const {
                                primary: modifierPrimary,
                                secondary: modifierSecondary,
                              } = resolveModifierDisplay(chapter);

                              return (
                                <TableRow key={chapter.outline_item_bid}>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/80 last:border-r-0'
                                    style={getChapterColumnStyle('position')}
                                  >
                                    {chapter.position || emptyValue}
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 border-r border-border last:border-r-0'
                                    style={getChapterColumnStyle('name')}
                                  >
                                    <div
                                      className='flex min-w-0 items-center justify-center gap-2'
                                      style={{
                                        paddingLeft: `${chapter.depth * 20}px`,
                                      }}
                                    >
                                      <Badge
                                        variant='outline'
                                        className='shrink-0 rounded-full border-border/60 bg-background px-1.5 py-0 text-[10px] font-medium text-muted-foreground'
                                      >
                                        {resolveChapterTypeLabel(
                                          chapter.node_type,
                                        )}
                                      </Badge>
                                      <AdminTooltipText
                                        text={chapter.title || emptyValue}
                                        emptyValue={emptyValue}
                                        className='text-center text-sm font-medium text-foreground'
                                      />
                                    </div>
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                                    style={getChapterColumnStyle(
                                      'learningPermission',
                                    )}
                                  >
                                    {resolveLearningPermissionLabel(
                                      chapter.learning_permission,
                                    )}
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                                    style={getChapterColumnStyle('visibility')}
                                  >
                                    {chapter.is_visible
                                      ? tOperations('detail.visibility.visible')
                                      : tOperations('detail.visibility.hidden')}
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                                    style={getChapterColumnStyle(
                                      'contentStatus',
                                    )}
                                  >
                                    {resolveContentStatusLabel(
                                      chapter.content_status,
                                    )}
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap border-r border-border text-center last:border-r-0'
                                    style={getChapterColumnStyle(
                                      'contentDetail',
                                    )}
                                  >
                                    <button
                                      type='button'
                                      className='text-sm text-primary transition-colors hover:text-primary/80'
                                      onClick={() =>
                                        setSelectedChapter(chapter)
                                      }
                                    >
                                      {tOperations(
                                        'detail.chaptersTable.detailAction',
                                      )}
                                    </button>
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 border-r border-border text-center last:border-r-0'
                                    style={getChapterColumnStyle('modifier')}
                                  >
                                    <div className='flex flex-col gap-0.5 leading-tight'>
                                      <AdminTooltipText
                                        text={modifierPrimary}
                                        emptyValue={emptyValue}
                                        className='text-sm text-foreground'
                                      />
                                      {modifierSecondary ? (
                                        <AdminTooltipText
                                          text={modifierSecondary}
                                          emptyValue={emptyValue}
                                          className='text-xs text-muted-foreground'
                                        />
                                      ) : null}
                                    </div>
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                                    style={getChapterColumnStyle('updatedAt')}
                                  >
                                    <AdminTooltipText
                                      text={
                                        formatAdminUtcDateTime(
                                          chapter.updated_at,
                                        ) || emptyValue
                                      }
                                      emptyValue={emptyValue}
                                      className='mx-auto block max-w-full'
                                    />
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap border-l-2 border-l-border/80 border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                                    style={getChapterColumnStyle(
                                      'followUpCount',
                                    )}
                                  >
                                    {chapter.node_type === 'chapter'
                                      ? emptyValue
                                      : formatCount(chapter.follow_up_count)}
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                                    style={getChapterColumnStyle('ratingScore')}
                                  >
                                    {chapter.node_type === 'chapter'
                                      ? emptyValue
                                      : chapter.rating_score || emptyValue}
                                  </TableCell>
                                  <TableCell
                                    className='py-2.5 whitespace-nowrap text-center text-sm text-muted-foreground/75'
                                    style={getChapterColumnStyle('ratingCount')}
                                  >
                                    {chapter.node_type === 'chapter'
                                      ? emptyValue
                                      : formatCount(chapter.rating_count)}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      )}
                    />
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent
                value='users'
                className='mt-0'
              >
                <Card className='overflow-hidden border-border/80 shadow-sm ring-1 ring-border/40'>
                  <CardHeader className='gap-1.5 border-b border-border/70 bg-muted/[0.08] px-6 pb-2.5 pt-4'>
                    <div className='flex flex-col gap-1 md:flex-row md:items-baseline md:gap-3'>
                      <CardTitle className='text-base font-semibold tracking-normal'>
                        {tOperations('detail.users')}
                      </CardTitle>
                      <p className='text-sm text-muted-foreground'>
                        {tOperations('detail.usersDescription')}
                      </p>
                    </div>
                  </CardHeader>
                  <CardContent className='space-y-3 px-6 pb-6 pt-2.5'>
                    <form
                      className='rounded-xl border border-border bg-muted/20 p-3'
                      onSubmit={event => {
                        event.preventDefault();
                        handleCourseUserSearch();
                      }}
                    >
                      <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-4'>
                        <div className='flex flex-col gap-2'>
                          <Label className='text-xs font-medium text-muted-foreground'>
                            {tOperations('detail.usersFilters.userKeyword')}
                          </Label>
                          <ClearableTextInput
                            value={courseUserFiltersDraft.keyword}
                            placeholder={courseUserKeywordPlaceholder}
                            clearLabel={t(
                              'module.chat.lessonFeedbackClearInput',
                            )}
                            onChange={value =>
                              setCourseUserFiltersDraft(prev => ({
                                ...prev,
                                keyword: value,
                              }))
                            }
                          />
                        </div>
                        <div className='flex flex-col gap-2'>
                          <Label className='text-xs font-medium text-muted-foreground'>
                            {tOperations('detail.usersFilters.userRole')}
                          </Label>
                          <Select
                            value={courseUserFiltersDraft.userRole}
                            onValueChange={value =>
                              applyCourseUserSelectFilter({
                                userRole: value,
                              })
                            }
                          >
                            <SelectTrigger className='h-9'>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={FILTER_ALL_OPTION}>
                                {tOperations('detail.usersFilters.all')}
                              </SelectItem>
                              <SelectItem value='operator'>
                                {resolveCourseUserRoleLabel('operator')}
                              </SelectItem>
                              <SelectItem value='creator'>
                                {resolveCourseUserRoleLabel('creator')}
                              </SelectItem>
                              <SelectItem value='student'>
                                {resolveCourseUserRoleLabel('student')}
                              </SelectItem>
                              <SelectItem value='normal'>
                                {resolveCourseUserRoleLabel('normal')}
                              </SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className='flex flex-col gap-2'>
                          <Label className='text-xs font-medium text-muted-foreground'>
                            {tOperations('detail.usersFilters.learningStatus')}
                          </Label>
                          <Select
                            value={courseUserFiltersDraft.learningStatus}
                            onValueChange={value =>
                              applyCourseUserSelectFilter({
                                learningStatus: value,
                              })
                            }
                          >
                            <SelectTrigger className='h-9'>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={FILTER_ALL_OPTION}>
                                {tOperations('detail.usersFilters.all')}
                              </SelectItem>
                              <SelectItem value='not_started'>
                                {resolveCourseUserLearningStatusLabel(
                                  'not_started',
                                )}
                              </SelectItem>
                              <SelectItem value='learning'>
                                {resolveCourseUserLearningStatusLabel(
                                  'learning',
                                )}
                              </SelectItem>
                              <SelectItem value='completed'>
                                {resolveCourseUserLearningStatusLabel(
                                  'completed',
                                )}
                              </SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className='flex flex-col gap-2'>
                          <Label className='text-xs font-medium text-muted-foreground'>
                            {tOperations('detail.usersFilters.paymentStatus')}
                          </Label>
                          <Select
                            value={courseUserFiltersDraft.paymentStatus}
                            onValueChange={value =>
                              applyCourseUserSelectFilter({
                                paymentStatus: value as CourseUserPaymentStatus,
                              })
                            }
                          >
                            <SelectTrigger className='h-9'>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={FILTER_ALL_OPTION}>
                                {tOperations('detail.usersFilters.all')}
                              </SelectItem>
                              <SelectItem value='paid'>
                                {tOperations('detail.usersFilters.paymentPaid')}
                              </SelectItem>
                              <SelectItem value='unpaid'>
                                {tOperations(
                                  'detail.usersFilters.paymentUnpaid',
                                )}
                              </SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      <div className='mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4 xl:items-end'>
                        <div className='pl-3 text-sm text-muted-foreground xl:self-center'>
                          {tOperations('detail.usersCount', {
                            count: courseUsers.total,
                          })}
                        </div>
                        <div className='hidden xl:block' />
                        <div className='hidden xl:block' />
                        <div className='flex min-h-9 items-center justify-start gap-2 md:justify-end'>
                          <Button
                            type='button'
                            variant='outline'
                            className='h-9 px-4'
                            onClick={handleCourseUserReset}
                            disabled={courseUsersLoading}
                          >
                            {t('module.order.filters.reset')}
                          </Button>
                          <Button
                            type='submit'
                            className='h-9 px-4'
                            disabled={courseUsersLoading}
                          >
                            {t('module.order.filters.search')}
                          </Button>
                        </div>
                      </div>
                    </form>

                    <AdminTableShell
                      loading={courseUsersLoading}
                      isEmpty={!courseUsersError && courseUserRows.length === 0}
                      emptyContent={tOperations('detail.usersTable.empty')}
                      emptyColSpan={11}
                      withTooltipProvider={!courseUsersError}
                      tableWrapperClassName='overflow-auto'
                      loadingClassName='min-h-[240px]'
                      footer={
                        courseUserPageCount > 1 ? (
                          <AdminPagination
                            pageIndex={currentCourseUserPage}
                            pageCount={courseUserPageCount}
                            onPageChange={handleCourseUserPageChange}
                            prevLabel={t(
                              'module.order.paginationPrev',
                              'Previous',
                            )}
                            nextLabel={t('module.order.paginationNext', 'Next')}
                            prevAriaLabel={t(
                              'module.order.paginationPrevAriaLabel',
                              'Go to previous page',
                            )}
                            nextAriaLabel={t(
                              'module.order.paginationNextAriaLabel',
                              'Go to next page',
                            )}
                            className='mx-0 w-auto justify-end'
                          />
                        ) : null
                      }
                      table={
                        courseUsersError ? (
                          <div className='flex min-h-[240px] items-center justify-center p-6 text-center'>
                            <div className='space-y-2'>
                              <div className='text-sm font-medium text-destructive'>
                                {courseUsersError.message}
                              </div>
                              {typeof courseUsersError.code === 'number' ? (
                                <div className='text-xs text-muted-foreground'>
                                  {courseUsersError.code}
                                </div>
                              ) : null}
                            </div>
                          </div>
                        ) : (
                          emptyRow => (
                            <Table className='table-auto'>
                              <TableHeader>
                                <TableRow>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle('account')}
                                  >
                                    {courseUserAccountLabel}
                                    {renderUserResizeHandle('account')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle('nickname')}
                                  >
                                    {tOperations('detail.usersTable.nickname')}
                                    {renderUserResizeHandle('nickname')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle('userRole')}
                                  >
                                    {tOperations('detail.usersTable.userRole')}
                                    {renderUserResizeHandle('userRole')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle(
                                      'learningProgress',
                                    )}
                                  >
                                    {tOperations(
                                      'detail.usersTable.learningProgress',
                                    )}
                                    {renderUserResizeHandle('learningProgress')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle('learningStatus')}
                                  >
                                    {tOperations(
                                      'detail.usersTable.learningStatus',
                                    )}
                                    {renderUserResizeHandle('learningStatus')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle('isPaid')}
                                  >
                                    {tOperations('detail.usersTable.isPaid')}
                                    {renderUserResizeHandle('isPaid')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle(
                                      'totalPaidAmount',
                                    )}
                                  >
                                    {tOperations(
                                      'detail.usersTable.totalPaidAmount',
                                    )}
                                    {renderUserResizeHandle('totalPaidAmount')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle('lastLearnedAt')}
                                  >
                                    {tOperations(
                                      'detail.usersTable.lastLearnedAt',
                                    )}
                                    {renderUserResizeHandle('lastLearnedAt')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle('lastLoginAt')}
                                  >
                                    {tOperations(
                                      'detail.usersTable.lastLoginAt',
                                    )}
                                    {renderUserResizeHandle('lastLoginAt')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                                    )}
                                    style={getUserColumnStyle('joinedAt')}
                                  >
                                    {tOperations('detail.usersTable.joinedAt')}
                                    {renderUserResizeHandle('joinedAt')}
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      getAdminStickyRightHeaderClass(
                                        'h-10 whitespace-nowrap text-center text-xs',
                                      ),
                                    )}
                                    style={getUserColumnStyle('action')}
                                  >
                                    {tOperations('detail.usersTable.action')}
                                    {renderUserResizeHandle('action')}
                                  </TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {emptyRow}
                                {courseUserRows.map(row => (
                                  <TableRow key={row.user_bid}>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                                      style={getUserColumnStyle('account')}
                                    >
                                      <AdminTooltipText
                                        text={resolveCourseUserAccount(row)}
                                        emptyValue={emptyValue}
                                        className='mx-auto block max-w-[180px] font-semibold text-foreground'
                                      />
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                                      style={getUserColumnStyle('nickname')}
                                    >
                                      <AdminTooltipText
                                        text={row.nickname || defaultUserName}
                                        emptyValue={emptyValue}
                                        className='mx-auto block max-w-[140px]'
                                      />
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center last:border-r-0'
                                      style={getUserColumnStyle('userRole')}
                                    >
                                      <Badge
                                        variant='outline'
                                        className='border-0 bg-transparent px-0 py-0 text-xs font-medium text-foreground shadow-none'
                                      >
                                        {resolveCourseUserRoleLabel(
                                          row.user_role,
                                        )}
                                      </Badge>
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                                      style={getUserColumnStyle(
                                        'learningProgress',
                                      )}
                                    >
                                      <span className='font-medium tabular-nums text-foreground'>
                                        {formatLearningProgress(
                                          row.learned_lesson_count,
                                          row.total_lesson_count,
                                        )}
                                      </span>
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center last:border-r-0'
                                      style={getUserColumnStyle(
                                        'learningStatus',
                                      )}
                                    >
                                      <Badge
                                        variant='outline'
                                        className='border-0 bg-transparent px-0 py-0 text-xs font-medium text-foreground shadow-none'
                                      >
                                        {resolveCourseUserLearningStatusLabel(
                                          row.learning_status,
                                        )}
                                      </Badge>
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center text-xs font-medium text-muted-foreground/80 last:border-r-0'
                                      style={getUserColumnStyle('isPaid')}
                                    >
                                      {row.is_paid
                                        ? tOperations('detail.boolean.yes')
                                        : tOperations('detail.boolean.no')}
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                                      style={getUserColumnStyle(
                                        'totalPaidAmount',
                                      )}
                                    >
                                      <span className='font-medium tabular-nums text-foreground'>
                                        {resolveCourseUserPaidAmountDisplay(
                                          row,
                                        )}
                                      </span>
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center text-xs text-muted-foreground/65 last:border-r-0'
                                      style={getUserColumnStyle(
                                        'lastLearnedAt',
                                      )}
                                    >
                                      <AdminTooltipText
                                        text={formatAdminUtcDateTime(
                                          row.last_learning_at,
                                        )}
                                        emptyValue={emptyValue}
                                        className='mx-auto block max-w-full tabular-nums'
                                      />
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center text-xs text-muted-foreground/65 last:border-r-0'
                                      style={getUserColumnStyle('lastLoginAt')}
                                    >
                                      <AdminTooltipText
                                        text={formatAdminUtcDateTime(
                                          row.last_login_at,
                                        )}
                                        emptyValue={emptyValue}
                                        className='mx-auto block max-w-full tabular-nums'
                                      />
                                    </TableCell>
                                    <TableCell
                                      className='py-2.5 border-r border-border text-center text-xs text-muted-foreground/65 last:border-r-0'
                                      style={getUserColumnStyle('joinedAt')}
                                    >
                                      <AdminTooltipText
                                        text={formatAdminUtcDateTime(
                                          row.joined_at,
                                        )}
                                        emptyValue={emptyValue}
                                        className='mx-auto block max-w-full tabular-nums'
                                      />
                                    </TableCell>
                                    <TableCell
                                      className={getAdminStickyRightCellClass(
                                        'py-2.5 text-center text-sm text-muted-foreground/80',
                                      )}
                                      style={getUserColumnStyle('action')}
                                    >
                                      {emptyValue}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          )
                        )
                      }
                    />
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        </div>

        <Dialog
          open={Boolean(selectedChapter)}
          onOpenChange={open => {
            if (!open) {
              setSelectedChapter(null);
              setSelectedChapterDetail(EMPTY_CHAPTER_DETAIL);
            }
          }}
        >
          <DialogContent className={chapterDetailLayout.dialogClassName}>
            <DialogHeader className='border-b border-border px-6 py-4 pr-16'>
              <div className='flex items-center justify-between gap-4'>
                <DialogTitle>
                  {tOperations('detail.contentDetailDialog.title')}
                </DialogTitle>
                <DialogDescription className='sr-only'>
                  {selectedChapter?.title ||
                    tOperations('detail.contentDetailDialog.title')}
                </DialogDescription>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='gap-2'
                  onClick={handleCopyChapterDetail}
                  disabled={chapterDetailLoading || !selectedChapterCopyText}
                >
                  <Copy className='h-4 w-4' />
                  {tOperations('detail.contentDetailDialog.copy')}
                </Button>
              </div>
            </DialogHeader>
            <div className={chapterDetailLayout.bodyClassName}>
              {chapterDetailLoading ? (
                <div className='flex h-full min-h-[240px] items-center justify-center'>
                  <Loading />
                </div>
              ) : selectedChapterDetailSections.some(section =>
                  section.value.trim(),
                ) ? (
                <div className='space-y-5'>
                  {selectedChapterDetailSections.map(section => (
                    <section
                      key={section.label}
                      className='space-y-2'
                    >
                      <div className='text-sm font-medium text-foreground'>
                        {section.label}
                      </div>
                      <pre className='overflow-x-auto rounded-lg border border-border bg-muted/20 p-4 text-sm leading-6 text-foreground whitespace-pre-wrap break-words'>
                        {section.value.trim() ||
                          tOperations('detail.contentDetailDialog.empty')}
                      </pre>
                    </section>
                  ))}
                </div>
              ) : (
                <div className='flex h-full min-h-[240px] items-center justify-center text-sm text-muted-foreground'>
                  {tOperations('detail.contentDetailDialog.empty')}
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
