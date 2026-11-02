'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/components/admin/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminTitle from '@/app/admin/components/AdminTitle';
import AdminTableShell from '@/components/admin/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import CourseFeedbackSummaryCards from '@/app/admin/components/course-feedback/CourseFeedbackSummaryCards';
import FollowUpDetailSheet, {
  type FollowUpDetailSheetLabels,
} from '@/app/admin/components/course-feedback/FollowUpDetailSheet';
import FollowUpSourceStatusBadge from '@/app/admin/components/course-feedback/FollowUpSourceStatusBadge';
import StackedTooltipText from '@/app/admin/components/course-feedback/StackedTooltipText';
import {
  resolveRequestErrorState,
  useDisplayIdentifierType,
} from '@/app/admin/components/course-feedback/course-feedback-data';
import {
  hasChapterHierarchy as resolveHasChapterHierarchy,
  hasDistinctChapterTitle,
  resolvePrimaryAccount,
  resolvePrimaryLessonDisplay,
  resolveSecondaryChapterDisplay,
  type CourseFeedbackErrorState,
} from '@/app/admin/components/course-feedback/course-feedback-display';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/components/admin/admin-table-styles';
import { useAdminResizableColumns } from '@/app/admin/hooks/use-admin-resizable-columns';
import { formatAdminUtcDateTime } from '@/app/admin/lib/date-time';
import { formatAdminCount } from '@/app/admin/lib/number-format';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
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
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import AdminOperationsBreadcrumb from '../../AdminOperationsBreadcrumb';
import {
  buildAdminOperationsCourseDetailUrl,
  buildAdminOperationsCourseFollowUpsUrl,
} from '../../operation-course-routes';
import type {
  AdminOperationCourseFollowUpDetailResponse,
  AdminOperationCourseFollowUpItem,
  AdminOperationCourseFollowUpListResponse,
} from '../../operation-course-types';
import useOperatorGuard from '../../use-operator-guard';

type ErrorState = CourseFeedbackErrorState;
type FollowUpFilters = {
  keyword: string;
  chapterKeyword: string;
  sourceStatus: string;
  startTime: string;
  endTime: string;
};

const PAGE_SIZE = 20;
const ALL_SOURCE_STATUS = 'all';
const COLUMN_MIN_WIDTH = 80;
const COLUMN_MAX_WIDTH = 420;
const COLUMN_WIDTH_STORAGE_KEY = 'adminOperationCourseFollowUpColumnWidths';
const COLUMN_DEFAULT_WIDTHS = {
  createdAt: 170,
  user: 240,
  lesson: 240,
  content: 320,
  turnIndex: 120,
  action: 110,
} as const;

const EMPTY_FOLLOW_UPS_RESPONSE: AdminOperationCourseFollowUpListResponse = {
  summary: {
    follow_up_count: 0,
    user_count: 0,
    lesson_count: 0,
    latest_follow_up_at: '',
  },
  items: [],
  page: 1,
  page_size: PAGE_SIZE,
  total: 0,
  page_count: 0,
};

const EMPTY_FOLLOW_UP_DETAIL: AdminOperationCourseFollowUpDetailResponse = {
  basic_info: {
    generated_block_bid: '',
    progress_record_bid: '',
    user_bid: '',
    mobile: '',
    email: '',
    nickname: '',
    course_name: '',
    shifu_bid: '',
    chapter_title: '',
    lesson_title: '',
    created_at: '',
    turn_index: 0,
  },
  current_record: {
    follow_up_content: '',
    answer_content: '',
    source_output_content: '',
    source_output_type: '',
    source_position: 0,
    source_element_bid: '',
    source_element_type: '',
  },
  timeline: [],
};

const createFollowUpFilters = (): FollowUpFilters => ({
  keyword: '',
  chapterKeyword: '',
  sourceStatus: ALL_SOURCE_STATUS,
  startTime: '',
  endTime: '',
});

const normalizeFollowUpFilters = (
  filters: FollowUpFilters,
): FollowUpFilters => ({
  keyword: filters.keyword.trim(),
  chapterKeyword: filters.chapterKeyword.trim(),
  sourceStatus:
    filters.sourceStatus.trim() === ALL_SOURCE_STATUS
      ? ''
      : filters.sourceStatus.trim(),
  startTime: filters.startTime,
  endTime: filters.endTime,
});

const areFollowUpFiltersEqual = (
  first: FollowUpFilters,
  second: FollowUpFilters,
) =>
  first.keyword === second.keyword &&
  first.chapterKeyword === second.chapterKeyword &&
  first.sourceStatus === second.sourceStatus &&
  first.startTime === second.startTime &&
  first.endTime === second.endTime;

const isDefaultFollowUpFilters = (filters: FollowUpFilters) =>
  areFollowUpFiltersEqual(
    normalizeFollowUpFilters(filters),
    normalizeFollowUpFilters(createFollowUpFilters()),
  );

const formatCount = (value: number, locale: string): string =>
  formatAdminCount(value, locale);

/**
 * t('module.operationsCourse.detail.followUps.title')
 * t('module.operationsCourse.detail.followUps.openMetric')
 * t('module.operationsCourse.detail.followUps.summary.followUpCount')
 * t('module.operationsCourse.detail.followUps.summary.userCount')
 * t('module.operationsCourse.detail.followUps.summary.lessonCount')
 * t('module.operationsCourse.detail.followUps.summary.latestFollowUpAt')
 * t('module.operationsCourse.detail.followUps.filters.userKeyword')
 * t('module.operationsCourse.detail.followUps.filters.userKeywordPlaceholder')
 * t('module.operationsCourse.detail.followUps.filters.userKeywordPlaceholderPhone')
 * t('module.operationsCourse.detail.followUps.filters.userKeywordPlaceholderEmail')
 * t('module.operationsCourse.detail.followUps.filters.chapterKeyword')
 * t('module.operationsCourse.detail.followUps.filters.chapterKeywordPlaceholder')
 * t('module.operationsCourse.detail.followUps.filters.lessonKeyword')
 * t('module.operationsCourse.detail.followUps.filters.lessonKeywordPlaceholder')
 * t('module.operationsCourse.detail.followUps.filters.followUpTime')
 * t('module.operationsCourse.detail.followUps.filters.resultCount')
 * t('module.operationsCourse.detail.followUps.filters.timePlaceholder')
 * t('module.operationsCourse.detail.followUps.filters.search')
 * t('module.operationsCourse.detail.followUps.filters.reset')
 * t('module.operationsCourse.detail.followUps.table.title')
 * t('module.operationsCourse.detail.followUps.table.createdAt')
 * t('module.operationsCourse.detail.followUps.table.user')
 * t('module.operationsCourse.detail.followUps.table.lesson')
 * t('module.operationsCourse.detail.followUps.table.content')
 * t('module.operationsCourse.detail.followUps.table.turnIndex')
 * t('module.operationsCourse.detail.followUps.table.action')
 * t('module.operationsCourse.detail.followUps.table.detailAction')
 * t('module.operationsCourse.detail.followUps.table.empty')
 * t('module.operationsCourse.detail.followUps.emptyValue')
 * t('module.operationsCourse.detail.followUps.turnIndex')
 * t('module.operationsCourse.detail.followUps.turnIndexHelp')
 * t('module.user.defaultUserName')
 */
export default function AdminOperationCourseFollowUpsPage() {
  const router = useRouter();
  const params = useParams<{ shifu_bid?: string }>();
  const { t, i18n } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');
  const { isReady } = useOperatorGuard();

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = tOperations('detail.followUps.emptyValue');
  const clearLabel = t('common.core.close');
  const followUpsLoadErrorMessage = t(
    'module.operationsCourse.messages.loadFollowUpsFailed',
  );
  const followUpDetailLoadErrorMessage = t(
    'module.operationsCourse.messages.loadFollowUpDetailFailed',
  );
  const defaultUserName = t('module.user.defaultUserName');
  const displayIdentifierType = useDisplayIdentifierType();
  const detailPageUrl = useMemo(
    () => buildAdminOperationsCourseDetailUrl(shifuBid),
    [shifuBid],
  );
  const currentPageUrl = useMemo(
    () => buildAdminOperationsCourseFollowUpsUrl(shifuBid),
    [shifuBid],
  );
  const userKeywordPlaceholder = useMemo(
    () =>
      displayIdentifierType === 'email'
        ? tOperations('detail.followUps.filters.userKeywordPlaceholderEmail')
        : tOperations('detail.followUps.filters.userKeywordPlaceholderPhone'),
    [displayIdentifierType, tOperations],
  );

  const [followUps, setFollowUps] =
    useState<AdminOperationCourseFollowUpListResponse>(
      EMPTY_FOLLOW_UPS_RESPONSE,
    );
  const [fullSummary, setFullSummary] = useState(
    EMPTY_FOLLOW_UPS_RESPONSE.summary,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [pageIndex, setPageIndex] = useState(1);
  const [filtersDraft, setFiltersDraft] = useState<FollowUpFilters>(
    createFollowUpFilters,
  );
  const [filters, setFilters] = useState<FollowUpFilters>(
    createFollowUpFilters,
  );
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedGeneratedBlockBid, setSelectedGeneratedBlockBid] =
    useState('');
  const [detail, setDetail] =
    useState<AdminOperationCourseFollowUpDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ErrorState | null>(null);
  const listRequestIdRef = useRef(0);
  const detailRequestIdRef = useRef(0);
  const { getColumnStyle, getResizeHandleProps } = useAdminResizableColumns<
    keyof typeof COLUMN_DEFAULT_WIDTHS
  >({
    storageKey: COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: COLUMN_DEFAULT_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });

  const fetchFollowUps = useCallback(
    async (targetPage: number, nextFilters?: FollowUpFilters) => {
      if (!shifuBid.trim()) {
        setError({ message: followUpsLoadErrorMessage });
        setFollowUps(EMPTY_FOLLOW_UPS_RESPONSE);
        setFullSummary(EMPTY_FOLLOW_UPS_RESPONSE.summary);
        return;
      }

      const resolvedFilters = normalizeFollowUpFilters(nextFilters ?? filters);
      const shouldRefreshFullSummary =
        isDefaultFollowUpFilters(resolvedFilters);
      const requestId = listRequestIdRef.current + 1;
      listRequestIdRef.current = requestId;
      setLoading(true);
      setError(null);

      try {
        const response = (await api.getAdminOperationCourseFollowUps({
          shifu_bid: shifuBid,
          page: targetPage,
          page_size: PAGE_SIZE,
          include_summary: shouldRefreshFullSummary,
          keyword: resolvedFilters.keyword,
          chapter_keyword: resolvedFilters.chapterKeyword,
          source_status: resolvedFilters.sourceStatus,
          start_time: resolvedFilters.startTime,
          end_time: resolvedFilters.endTime,
        })) as AdminOperationCourseFollowUpListResponse;
        if (requestId !== listRequestIdRef.current) {
          return;
        }
        if (shouldRefreshFullSummary) {
          setFullSummary(
            response?.summary || EMPTY_FOLLOW_UPS_RESPONSE.summary,
          );
        }
        setFollowUps({
          summary: response?.summary || EMPTY_FOLLOW_UPS_RESPONSE.summary,
          items: response?.items || [],
          page: response?.page || targetPage,
          page_size: response?.page_size || PAGE_SIZE,
          total: response?.total || 0,
          page_count: response?.page_count || 0,
        });
      } catch (err) {
        if (requestId !== listRequestIdRef.current) {
          return;
        }
        setFollowUps(EMPTY_FOLLOW_UPS_RESPONSE);
        setError(resolveRequestErrorState(err, followUpsLoadErrorMessage));
      } finally {
        if (requestId === listRequestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [filters, shifuBid, followUpsLoadErrorMessage],
  );

  const fetchFollowUpDetail = useCallback(async () => {
    if (!shifuBid.trim() || !selectedGeneratedBlockBid.trim()) {
      setDetailError({ message: followUpDetailLoadErrorMessage });
      setDetail(EMPTY_FOLLOW_UP_DETAIL);
      setDetailLoading(false);
      return;
    }

    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    setDetailLoading(true);
    setDetailError(null);

    try {
      const response = (await api.getAdminOperationCourseFollowUpDetail({
        shifu_bid: shifuBid,
        generated_block_bid: selectedGeneratedBlockBid,
      })) as AdminOperationCourseFollowUpDetailResponse;
      if (requestId !== detailRequestIdRef.current) {
        return;
      }
      setDetail(response || EMPTY_FOLLOW_UP_DETAIL);
    } catch (err) {
      if (requestId !== detailRequestIdRef.current) {
        return;
      }
      setDetail(EMPTY_FOLLOW_UP_DETAIL);
      setDetailError(
        resolveRequestErrorState(err, followUpDetailLoadErrorMessage),
      );
    } finally {
      if (requestId === detailRequestIdRef.current) {
        setDetailLoading(false);
      }
    }
  }, [selectedGeneratedBlockBid, shifuBid, followUpDetailLoadErrorMessage]);

  useEffect(() => {
    if (!isReady) {
      return;
    }
    fetchFollowUps(pageIndex, filters);
  }, [fetchFollowUps, filters, isReady, pageIndex]);

  useEffect(() => {
    if (!isReady || !detailOpen || !selectedGeneratedBlockBid.trim()) {
      return;
    }
    fetchFollowUpDetail();
  }, [detailOpen, fetchFollowUpDetail, isReady, selectedGeneratedBlockBid]);

  const currentPage = followUps.page || 1;
  const pageCount = Math.max(followUps.page_count || 0, 1);
  const rows = useMemo(() => followUps.items || [], [followUps.items]);
  const hasChapterHierarchy = useMemo(
    () => resolveHasChapterHierarchy(rows),
    [rows],
  );
  const outlineFilterLabel = hasChapterHierarchy
    ? tOperations('detail.followUps.filters.chapterKeyword')
    : tOperations('detail.followUps.filters.lessonKeyword');
  const outlineFilterPlaceholder = hasChapterHierarchy
    ? tOperations('detail.followUps.filters.chapterKeywordPlaceholder')
    : tOperations('detail.followUps.filters.lessonKeywordPlaceholder');
  const turnIndexHelpText = tOperations('detail.followUps.turnIndexHelp');
  const tableScopeHint = tOperations('detail.followUps.table.scopeHint');
  const resolveDetailOutlineFieldLabel = useCallback(
    ({
      lessonTitle,
      chapterTitle,
    }: {
      lessonTitle?: string;
      chapterTitle?: string;
    }) =>
      hasDistinctChapterTitle({
        lesson_title: lessonTitle,
        chapter_title: chapterTitle,
      })
        ? tOperations('detail.followUps.drawer.fields.chapter')
        : tOperations('detail.followUps.drawer.fields.lesson'),
    [tOperations],
  );
  const detailSheetLabels = useMemo<FollowUpDetailSheetLabels>(
    () => ({
      title: tOperations('detail.followUps.drawer.title'),
      basicInfoSection: tOperations(
        'detail.followUps.drawer.sections.basicInfo',
      ),
      currentRecordSection: tOperations(
        'detail.followUps.drawer.sections.currentRecord',
      ),
      currentRecordHint: tOperations(
        'detail.followUps.drawer.currentRecordHint',
      ),
      timelineSection: tOperations('detail.followUps.drawer.sections.timeline'),
      user: tOperations('detail.followUps.drawer.fields.user'),
      nickname: tOperations('detail.followUps.drawer.fields.nickname'),
      userId: tOperations('detail.followUps.drawer.fields.userId'),
      followUpTime: tOperations('detail.followUps.drawer.fields.followUpTime'),
      turnIndex: tOperations('detail.followUps.drawer.fields.turnIndex'),
      turnIndexHelp: turnIndexHelpText,
      sourceOutput: {
        title: tOperations('detail.followUps.drawer.fields.sourceOutput'),
        unavailable: tOperations('detail.followUps.drawer.sourceUnavailable'),
      },
      currentFollowUp: tOperations(
        'detail.followUps.drawer.fields.currentFollowUp',
      ),
      currentAnswer: tOperations(
        'detail.followUps.drawer.fields.currentAnswer',
      ),
      timelineCurrent: tOperations('detail.followUps.drawer.timeline.current'),
    }),
    [tOperations, turnIndexHelpText],
  );
  const formatDetailTurnIndex = useCallback(
    (turnIndex: number | null | undefined) =>
      turnIndex
        ? tOperations('detail.followUps.turnIndex', { count: turnIndex })
        : emptyValue,
    [emptyValue, tOperations],
  );
  const resolveDetailRoleLabel = useCallback(
    (role: string) => {
      if (role === 'student') {
        return tOperations('detail.followUps.drawer.timeline.student');
      }
      if (role === 'teacher') {
        return tOperations('detail.followUps.drawer.timeline.teacher');
      }
      return role;
    },
    [tOperations],
  );
  const userKeywordInputId = 'follow-up-user-keyword-filter';
  const outlineKeywordInputId = 'follow-up-outline-keyword-filter';
  const sourceStatusSelectId = 'follow-up-source-status-filter';
  const followUpTimeFilterAriaLabel = tOperations(
    'detail.followUps.filters.followUpTime',
  );
  const summaryCards = useMemo(
    () => [
      {
        key: 'followUpCount',
        label: tOperations('detail.followUps.summary.followUpCount'),
        value: formatCount(fullSummary.follow_up_count, i18n.language),
        tone: 'value' as const,
      },
      {
        key: 'userCount',
        label: tOperations('detail.followUps.summary.userCount'),
        value: formatCount(fullSummary.user_count, i18n.language),
        tone: 'value' as const,
      },
      {
        key: 'lessonCount',
        label: tOperations('detail.followUps.summary.lessonCount'),
        value: formatCount(fullSummary.lesson_count, i18n.language),
        tone: 'value' as const,
      },
      {
        key: 'latestFollowUpAt',
        label: tOperations('detail.followUps.summary.latestFollowUpAt'),
        value:
          formatAdminUtcDateTime(fullSummary.latest_follow_up_at) || emptyValue,
        tone: 'timestamp' as const,
      },
    ],
    [emptyValue, fullSummary, i18n.language, tOperations],
  );

  const resolveUserSecondary = useCallback(
    (item: AdminOperationCourseFollowUpItem) =>
      item.nickname?.trim() || defaultUserName,
    [defaultUserName],
  );

  const handleSearch = useCallback(() => {
    const nextFilters = normalizeFollowUpFilters(filtersDraft);
    if (pageIndex === 1 && areFollowUpFiltersEqual(nextFilters, filters)) {
      return;
    }
    setFilters(nextFilters);
    setPageIndex(1);
  }, [filters, filtersDraft, pageIndex]);

  const handleReset = useCallback(() => {
    const nextFilters = createFollowUpFilters();
    if (
      pageIndex === 1 &&
      areFollowUpFiltersEqual(nextFilters, filters) &&
      areFollowUpFiltersEqual(nextFilters, filtersDraft)
    ) {
      return;
    }
    setFiltersDraft(nextFilters);
    if (pageIndex === 1 && areFollowUpFiltersEqual(nextFilters, filters)) {
      return;
    }
    setFilters(nextFilters);
    setPageIndex(1);
  }, [filters, filtersDraft, pageIndex]);

  const handlePageChange = useCallback(
    (nextPage: number) => {
      if (nextPage < 1 || nextPage > pageCount || nextPage === currentPage) {
        return;
      }
      setPageIndex(nextPage);
    },
    [currentPage, pageCount],
  );

  const handleOpenDetail = useCallback(
    (generatedBlockBid: string) => {
      const normalizedGeneratedBlockBid = generatedBlockBid.trim();
      if (!normalizedGeneratedBlockBid) {
        detailRequestIdRef.current += 1;
        setSelectedGeneratedBlockBid('');
        setDetail(EMPTY_FOLLOW_UP_DETAIL);
        setDetailError({ message: followUpDetailLoadErrorMessage });
        setDetailLoading(false);
        setDetailOpen(false);
        return;
      }

      detailRequestIdRef.current += 1;
      setSelectedGeneratedBlockBid(normalizedGeneratedBlockBid);
      setDetail(null);
      setDetailError(null);
      setDetailLoading(true);
      setDetailOpen(true);
    },
    [followUpDetailLoadErrorMessage],
  );

  const handleDetailOpenChange = useCallback((open: boolean) => {
    setDetailOpen(open);
    if (!open) {
      detailRequestIdRef.current += 1;
      setSelectedGeneratedBlockBid('');
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
    }
  }, []);

  const renderResizeHandle = useCallback(
    (columnKey: keyof typeof COLUMN_DEFAULT_WIDTHS) => {
      return (
        <span
          className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
          {...getResizeHandleProps(columnKey)}
        />
      );
    },
    [getResizeHandleProps],
  );

  if (!isReady) {
    return <Loading />;
  }

  if (!currentPageUrl) {
    return (
      <div className='p-6'>
        <ErrorDisplay
          errorCode={0}
          errorMessage={followUpsLoadErrorMessage}
          onRetry={() => router.push('/admin/operations')}
        />
      </div>
    );
  }

  return (
    <div className='h-full min-h-0 overflow-hidden bg-stone-50 p-0 overscroll-none'>
      <div className='mx-auto flex h-full min-h-0 w-full max-w-7xl flex-col overflow-hidden'>
        <AdminOperationsBreadcrumb
          items={[
            {
              label: tOperations('title'),
              href: '/admin/operations',
            },
            {
              label: tOperations('detail.title'),
              href: detailPageUrl || undefined,
            },
            { label: tOperations('detail.followUps.title') },
          ]}
        />
        <AdminTitle title={tOperations('detail.followUps.title')} />

        <div className='min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain pr-1'>
          <div className='space-y-5 pb-6'>
            <CourseFeedbackSummaryCards
              cards={summaryCards}
              gridClassName='grid gap-4 md:grid-cols-2 xl:grid-cols-4'
              size='comfortable'
            />

            <Card className='overflow-hidden border-border/80 shadow-sm'>
              <CardHeader className='pb-3'>
                <div className='space-y-0.5'>
                  <CardTitle className='text-base font-semibold tracking-normal'>
                    {tOperations('detail.followUps.table.title')}
                  </CardTitle>
                  <p className='text-xs leading-5 text-muted-foreground/85'>
                    {tableScopeHint}
                  </p>
                  <p className='text-xs leading-5 text-muted-foreground/85'>
                    {turnIndexHelpText}
                  </p>
                </div>
              </CardHeader>
              <CardContent className='space-y-5 pt-0'>
                <form
                  className='rounded-xl border border-border bg-muted/20 p-3'
                  onSubmit={event => {
                    event.preventDefault();
                    handleSearch();
                  }}
                >
                  <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-4'>
                    <div className='flex flex-col gap-2'>
                      <label
                        htmlFor={userKeywordInputId}
                        className='text-xs font-medium text-muted-foreground'
                      >
                        {tOperations('detail.followUps.filters.userKeyword')}
                      </label>
                      <AdminClearableInput
                        id={userKeywordInputId}
                        value={filtersDraft.keyword}
                        placeholder={userKeywordPlaceholder}
                        clearLabel={clearLabel}
                        onChange={value =>
                          setFiltersDraft(previous => ({
                            ...previous,
                            keyword: value,
                          }))
                        }
                        onSubmit={handleSearch}
                      />
                    </div>
                    <div className='flex flex-col gap-2'>
                      <label
                        htmlFor={outlineKeywordInputId}
                        className='text-xs font-medium text-muted-foreground'
                      >
                        {outlineFilterLabel}
                      </label>
                      <AdminClearableInput
                        id={outlineKeywordInputId}
                        value={filtersDraft.chapterKeyword}
                        placeholder={outlineFilterPlaceholder}
                        clearLabel={clearLabel}
                        onChange={value =>
                          setFiltersDraft(previous => ({
                            ...previous,
                            chapterKeyword: value,
                          }))
                        }
                        onSubmit={handleSearch}
                      />
                    </div>
                    <div className='flex flex-col gap-2'>
                      <label
                        htmlFor={sourceStatusSelectId}
                        className='text-xs font-medium text-muted-foreground'
                      >
                        {tOperations('detail.followUps.filters.sourceStatus')}
                      </label>
                      <Select
                        value={filtersDraft.sourceStatus}
                        onValueChange={value =>
                          setFiltersDraft(previous => ({
                            ...previous,
                            sourceStatus: value,
                          }))
                        }
                      >
                        <SelectTrigger
                          id={sourceStatusSelectId}
                          className='h-9'
                        >
                          <SelectValue
                            placeholder={tOperations(
                              'detail.followUps.filters.sourceStatusAll',
                            )}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={ALL_SOURCE_STATUS}>
                            {tOperations(
                              'detail.followUps.filters.sourceStatusAll',
                            )}
                          </SelectItem>
                          <SelectItem value='resolved'>
                            {tOperations(
                              'detail.followUps.filters.sourceStatusResolved',
                            )}
                          </SelectItem>
                          <SelectItem value='missing'>
                            {tOperations(
                              'detail.followUps.filters.sourceStatusMissing',
                            )}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className='flex flex-col gap-2'>
                      <label className='text-xs font-medium text-muted-foreground'>
                        {tOperations('detail.followUps.filters.followUpTime')}
                      </label>
                      <AdminDateRangeFilter
                        startValue={filtersDraft.startTime}
                        endValue={filtersDraft.endTime}
                        triggerAriaLabel={followUpTimeFilterAriaLabel}
                        placeholder={tOperations(
                          'detail.followUps.filters.timePlaceholder',
                        )}
                        resetLabel={tOperations(
                          'detail.followUps.filters.reset',
                        )}
                        clearLabel={clearLabel}
                        onChange={({ start, end }) =>
                          setFiltersDraft(previous => ({
                            ...previous,
                            startTime: start,
                            endTime: end,
                          }))
                        }
                      />
                    </div>
                  </div>

                  <div className='mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4 xl:items-end'>
                    <div className='pl-3 text-sm text-muted-foreground xl:self-center'>
                      {tOperations('detail.followUps.filters.resultCount', {
                        count: followUps.total,
                      })}
                    </div>
                    <div className='hidden xl:block' />
                    <div className='hidden xl:block' />
                    <div className='flex min-h-9 items-center justify-start gap-2 md:justify-end'>
                      <Button
                        type='button'
                        size='sm'
                        variant='outline'
                        className='h-9 px-4'
                        onClick={handleReset}
                        disabled={loading}
                      >
                        {tOperations('detail.followUps.filters.reset')}
                      </Button>
                      <Button
                        type='submit'
                        size='sm'
                        className='h-9 px-4'
                        disabled={loading}
                      >
                        {tOperations('detail.followUps.filters.search')}
                      </Button>
                    </div>
                  </div>
                </form>

                {error ? (
                  <ErrorDisplay
                    errorCode={error.code || 0}
                    errorMessage={error.message}
                    onRetry={() => fetchFollowUps(pageIndex, filters)}
                  />
                ) : (
                  <AdminTableShell
                    loading={loading}
                    isEmpty={rows.length === 0}
                    emptyContent={tOperations('detail.followUps.table.empty')}
                    emptyColSpan={Object.keys(COLUMN_DEFAULT_WIDTHS).length}
                    withTooltipProvider
                    tableWrapperClassName='overflow-auto'
                    loadingClassName='min-h-[240px]'
                    table={emptyRow => (
                      <Table className='table-auto'>
                        <TableHeader>
                          <TableRow>
                            <TableHead
                              className={cn(
                                ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('createdAt')}
                            >
                              {tOperations('detail.followUps.table.createdAt')}
                              {renderResizeHandle('createdAt')}
                            </TableHead>
                            <TableHead
                              className={cn(
                                ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('user')}
                            >
                              {tOperations('detail.followUps.table.user')}
                              {renderResizeHandle('user')}
                            </TableHead>
                            <TableHead
                              className={cn(
                                ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('lesson')}
                            >
                              {tOperations('detail.followUps.table.lesson')}
                              {renderResizeHandle('lesson')}
                            </TableHead>
                            <TableHead
                              className={cn(
                                ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('content')}
                            >
                              {tOperations('detail.followUps.table.content')}
                              {renderResizeHandle('content')}
                            </TableHead>
                            <TableHead
                              className={cn(
                                ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('turnIndex')}
                            >
                              {tOperations('detail.followUps.table.turnIndex')}
                              {renderResizeHandle('turnIndex')}
                            </TableHead>
                            <TableHead
                              className={cn(
                                getAdminStickyRightHeaderClass(
                                  ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
                                ),
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('action')}
                            >
                              {tOperations('detail.followUps.table.action')}
                              {renderResizeHandle('action')}
                            </TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {rows.length === 0
                            ? emptyRow
                            : rows.map(item => {
                                const primaryAccount = resolvePrimaryAccount({
                                  mobile: item.mobile,
                                  email: item.email,
                                  userBid: item.user_bid,
                                  displayIdentifierType,
                                  emptyValue,
                                });
                                const secondaryAccount =
                                  resolveUserSecondary(item);
                                const primaryLessonDisplay =
                                  resolvePrimaryLessonDisplay({
                                    lessonTitle: item.lesson_title,
                                    chapterTitle: item.chapter_title,
                                    emptyValue,
                                  });
                                const secondaryChapterDisplay =
                                  resolveSecondaryChapterDisplay({
                                    chapterTitle: item.chapter_title,
                                    lessonTitle: item.lesson_title,
                                  });
                                const turnIndexLabel = item.turn_index
                                  ? tOperations('detail.followUps.turnIndex', {
                                      count: item.turn_index,
                                    })
                                  : emptyValue;
                                return (
                                  <TableRow key={item.generated_block_bid}>
                                    <TableCell
                                      className='whitespace-nowrap border-r border-border py-3 text-center align-top text-sm text-foreground/80 last:border-r-0'
                                      style={getColumnStyle('createdAt')}
                                    >
                                      <AdminTooltipText
                                        text={formatAdminUtcDateTime(
                                          item.created_at,
                                        )}
                                        emptyValue={emptyValue}
                                        className='mx-auto block max-w-full'
                                      />
                                    </TableCell>
                                    <TableCell
                                      className='border-r border-border py-3 text-center align-top last:border-r-0'
                                      style={getColumnStyle('user')}
                                    >
                                      <StackedTooltipText
                                        primary={primaryAccount}
                                        primaryEmptyValue={emptyValue}
                                        primaryClassName='mx-auto block max-w-full text-sm text-foreground'
                                        secondary={secondaryAccount}
                                        secondaryEmptyValue={emptyValue}
                                        secondaryClassName='mx-auto block max-w-full text-xs text-muted-foreground'
                                        wrapSecondary
                                      />
                                    </TableCell>
                                    <TableCell
                                      className='border-r border-border py-3 align-middle last:border-r-0'
                                      style={getColumnStyle('lesson')}
                                    >
                                      <StackedTooltipText
                                        primary={primaryLessonDisplay}
                                        primaryEmptyValue={emptyValue}
                                        primaryClassName='block max-w-full text-sm text-foreground'
                                        secondary={secondaryChapterDisplay}
                                        secondaryEmptyValue={emptyValue}
                                        secondaryClassName='block max-w-full text-xs text-muted-foreground'
                                      />
                                    </TableCell>
                                    <TableCell
                                      className='border-r border-border py-3 align-top last:border-r-0'
                                      style={getColumnStyle('content')}
                                    >
                                      <button
                                        type='button'
                                        className='group block w-full rounded-lg px-2 py-1.5 text-center transition-colors hover:bg-primary/[0.05]'
                                        onClick={() =>
                                          handleOpenDetail(
                                            item.generated_block_bid,
                                          )
                                        }
                                      >
                                        <AdminTooltipText
                                          text={item.follow_up_content}
                                          emptyValue={emptyValue}
                                          className='mx-auto block max-w-full text-sm font-medium text-foreground transition-colors group-hover:text-primary'
                                        />
                                        <div className='mt-2 flex justify-center'>
                                          <FollowUpSourceStatusBadge
                                            hasSourceOutput={
                                              item.has_source_output
                                            }
                                            resolvedLabel={tOperations(
                                              'detail.followUps.table.sourceResolved',
                                            )}
                                            missingLabel={tOperations(
                                              'detail.followUps.table.sourceMissing',
                                            )}
                                          />
                                        </div>
                                      </button>
                                    </TableCell>
                                    <TableCell
                                      className='whitespace-nowrap border-r border-border py-3 text-center align-top text-sm text-foreground last:border-r-0'
                                      style={getColumnStyle('turnIndex')}
                                    >
                                      {turnIndexLabel}
                                    </TableCell>
                                    <TableCell
                                      className={cn(
                                        getAdminStickyRightCellClass(
                                          'border-l border-border py-3 text-center align-top',
                                        ),
                                      )}
                                      style={getColumnStyle('action')}
                                    >
                                      <Button
                                        type='button'
                                        variant='link'
                                        className='h-auto px-0 py-0 text-sm'
                                        onClick={() =>
                                          handleOpenDetail(
                                            item.generated_block_bid,
                                          )
                                        }
                                      >
                                        {tOperations(
                                          'detail.followUps.table.detailAction',
                                        )}
                                      </Button>
                                    </TableCell>
                                  </TableRow>
                                );
                              })}
                        </TableBody>
                      </Table>
                    )}
                    pagination={{
                      pageIndex: currentPage,
                      pageCount,
                      onPageChange: handlePageChange,
                      prevLabel: t('module.order.paginationPrev'),
                      nextLabel: t('module.order.paginationNext'),
                      prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
                      nextAriaLabel: t('module.order.paginationNextAriaLabel'),
                      hideWhenSinglePage: true,
                    }}
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      <FollowUpDetailSheet
        open={detailOpen}
        detail={detail}
        loading={detailLoading}
        error={detailError}
        emptyValue={emptyValue}
        displayIdentifierType={displayIdentifierType}
        defaultUserName={defaultUserName}
        labels={detailSheetLabels}
        resolveLessonDisplay={resolvePrimaryLessonDisplay}
        resolveOutlineFieldLabel={resolveDetailOutlineFieldLabel}
        formatTurnIndex={formatDetailTurnIndex}
        resolveRoleLabel={resolveDetailRoleLabel}
        onRetry={fetchFollowUpDetail}
        onOpenChange={handleDetailOpenChange}
      />
    </div>
  );
}
