'use client';

import { formatAdminUtcDateTime } from '@/app/admin/lib/date-time';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminFilter, {
  type AdminFilterItem,
} from '@/app/admin/components/AdminFilter';
import { AdminPagination } from '@/components/admin/AdminPagination';
import AdminTableShell from '@/components/admin/AdminTableShell';
import AdminTitle from '@/app/admin/components/AdminTitle';
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
  formatDisplayValue,
  hasChapterHierarchy as resolveHasChapterHierarchy,
  resolvePrimaryAccount,
  resolvePrimaryLessonDisplay,
  resolveSecondaryChapterDisplay,
  type CourseFeedbackErrorState,
} from '@/app/admin/components/course-feedback/course-feedback-display';
import {
  createDateRangeFilterItem,
  createSelectFilterItem,
  createTextFilterItem,
} from '@/app/admin/components/admin-filter-field-builders';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { useUserStore } from '@/store';
import type {
  DashboardCourseFollowUpDetailResponse,
  DashboardCourseFollowUpItem,
  DashboardCourseFollowUpListResponse,
} from '@/types/dashboard';
import {
  DASHBOARD_FILTER_CONTENT_CLASS,
  DASHBOARD_DETAIL_SUMMARY_GRID_CLASS,
  DASHBOARD_FILTER_ACTION_BUTTON_CLASS,
  DASHBOARD_FILTER_ACTIONS_CLASS,
  DASHBOARD_FILTER_FOLLOW_UPS_GRID_CLASS,
  DASHBOARD_FILTER_FOOTER_CLASS,
  DASHBOARD_FILTER_LABEL_CLASS,
  DASHBOARD_FILTER_LABEL_STANDARD_CLASS,
  DASHBOARD_FILTER_PANEL_CLASS,
  DASHBOARD_FILTER_RESULT_COUNT_CLASS,
  DASHBOARD_FILTER_SELECT_CONTENT_CLASS,
  DASHBOARD_FILTER_TEXT_CONTENT_BALANCED_CLASS,
  DASHBOARD_FILTER_TEXT_CONTENT_LEAD_CLASS,
} from '../../dashboard-filter-ui-shared';

type ErrorState = CourseFeedbackErrorState;
type FollowUpFilters = {
  userBid: string;
  keyword: string;
  chapterKeyword: string;
  sourceStatus: string;
  startTime: string;
  endTime: string;
};

const PAGE_SIZE = 20;
const ALL_SOURCE_STATUS = 'all';
const DETAIL_CACHE_LIMIT = 20;
const FOLLOW_UP_SOURCE_STATUS_LABEL_ID = 'follow-ups-source-status-label';
const FOLLOW_UP_SOURCE_STATUS_TRIGGER_ID = 'follow-ups-source-status-trigger';
const EMPTY_FOLLOW_UPS_RESPONSE: DashboardCourseFollowUpListResponse = {
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

const EMPTY_FOLLOW_UP_DETAIL: DashboardCourseFollowUpDetailResponse = {
  basic_info: {
    generated_block_bid: '',
    progress_record_bid: '',
    user_bid: '',
    mobile: '',
    email: '',
    nickname: '',
    chapter_title: '',
    lesson_title: '',
    created_at: '',
    turn_index: 0,
  },
  current_record: {
    follow_up_content: '',
    answer_content: '',
  },
  timeline: [],
};

const createFollowUpFilters = (
  values?: Partial<FollowUpFilters>,
): FollowUpFilters => ({
  userBid: values?.userBid?.trim() || '',
  keyword: values?.keyword?.trim() || '',
  chapterKeyword: values?.chapterKeyword?.trim() || '',
  sourceStatus: values?.sourceStatus?.trim() || ALL_SOURCE_STATUS,
  startTime: values?.startTime?.trim() || '',
  endTime: values?.endTime?.trim() || '',
});

export default function AdminDashboardCourseFollowUpsPage() {
  const { t } = useTranslation();
  const params = useParams<{ shifu_bid?: string }>();
  const searchParams = useSearchParams();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = '--';
  const clearLabel = t('common.core.close');
  const followUpsLoadErrorMessage = t(
    'module.dashboard.messages.loadFollowUpsFailed',
  );
  const followUpDetailLoadErrorMessage = t(
    'module.dashboard.messages.loadFollowUpDetailFailed',
  );
  const defaultUserName = t('module.user.defaultUserName');
  const displayIdentifierType = useDisplayIdentifierType();
  const initialFilters = useMemo(
    () =>
      createFollowUpFilters({
        userBid: searchParams.get('user_bid') || '',
        keyword: searchParams.get('keyword') || '',
        chapterKeyword: searchParams.get('chapter_keyword') || '',
        sourceStatus: searchParams.get('source_status') || '',
        startTime: searchParams.get('start_time') || '',
        endTime: searchParams.get('end_time') || '',
      }),
    [searchParams],
  );
  const userKeywordPlaceholder = useMemo(
    () =>
      displayIdentifierType === 'email'
        ? t(
            'module.dashboard.detail.followUps.filters.userKeywordPlaceholderEmail',
          )
        : t(
            'module.dashboard.detail.followUps.filters.userKeywordPlaceholderPhone',
          ),
    [displayIdentifierType, t],
  );

  const [followUps, setFollowUps] =
    useState<DashboardCourseFollowUpListResponse>(EMPTY_FOLLOW_UPS_RESPONSE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [pageIndex, setPageIndex] = useState(1);
  const [filtersDraft, setFiltersDraft] =
    useState<FollowUpFilters>(initialFilters);
  const [filters, setFilters] = useState<FollowUpFilters>(initialFilters);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedGeneratedBlockBid, setSelectedGeneratedBlockBid] =
    useState('');
  const [detail, setDetail] =
    useState<DashboardCourseFollowUpDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ErrorState | null>(null);
  const listRequestIdRef = useRef(0);
  const detailRequestIdRef = useRef(0);
  const detailCacheRef = useRef(
    new Map<string, DashboardCourseFollowUpDetailResponse>(),
  );

  useEffect(() => {
    setFiltersDraft(initialFilters);
    setFilters(initialFilters);
    setPageIndex(1);
  }, [initialFilters]);

  const fetchFollowUps = useCallback(
    async (targetPage: number, nextFilters?: FollowUpFilters) => {
      if (!shifuBid.trim()) {
        setError({ message: followUpsLoadErrorMessage });
        setFollowUps(EMPTY_FOLLOW_UPS_RESPONSE);
        return;
      }

      const resolvedFilters = nextFilters ?? filters;
      const requestId = listRequestIdRef.current + 1;
      listRequestIdRef.current = requestId;
      setLoading(true);
      setError(null);

      try {
        const response = (await api.getDashboardCourseFollowUps({
          shifu_bid: shifuBid,
          page_index: targetPage,
          page_size: PAGE_SIZE,
          user_bid: resolvedFilters.userBid,
          keyword: resolvedFilters.keyword.trim(),
          chapter_keyword: resolvedFilters.chapterKeyword.trim(),
          source_status:
            resolvedFilters.sourceStatus.trim() === ALL_SOURCE_STATUS
              ? ''
              : resolvedFilters.sourceStatus.trim(),
          start_time: resolvedFilters.startTime,
          end_time: resolvedFilters.endTime,
        })) as DashboardCourseFollowUpListResponse;
        if (requestId !== listRequestIdRef.current) {
          return;
        }
        setFollowUps(response || EMPTY_FOLLOW_UPS_RESPONSE);
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

  const fetchFollowUpDetail = useCallback(
    async ({ forceRefresh = false }: { forceRefresh?: boolean } = {}) => {
      if (!shifuBid.trim() || !selectedGeneratedBlockBid.trim()) {
        setDetailError({ message: followUpDetailLoadErrorMessage });
        setDetail(EMPTY_FOLLOW_UP_DETAIL);
        setDetailLoading(false);
        return;
      }

      if (!forceRefresh) {
        const cachedDetail = detailCacheRef.current.get(
          selectedGeneratedBlockBid,
        );
        if (cachedDetail) {
          detailCacheRef.current.delete(selectedGeneratedBlockBid);
          detailCacheRef.current.set(selectedGeneratedBlockBid, cachedDetail);
          return;
        }
      }

      const requestId = detailRequestIdRef.current + 1;
      detailRequestIdRef.current = requestId;
      setDetailLoading(true);
      setDetailError(null);

      try {
        const response = (await api.getDashboardCourseFollowUpDetail({
          shifu_bid: shifuBid,
          generated_block_bid: selectedGeneratedBlockBid,
        })) as DashboardCourseFollowUpDetailResponse;
        if (requestId !== detailRequestIdRef.current) {
          return;
        }
        const resolvedDetail = response || EMPTY_FOLLOW_UP_DETAIL;
        detailCacheRef.current.delete(selectedGeneratedBlockBid);
        detailCacheRef.current.set(selectedGeneratedBlockBid, resolvedDetail);
        if (detailCacheRef.current.size > DETAIL_CACHE_LIMIT) {
          const oldestKey = detailCacheRef.current.keys().next().value;
          if (oldestKey) {
            detailCacheRef.current.delete(oldestKey);
          }
        }
        setDetail(resolvedDetail);
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
    },
    [selectedGeneratedBlockBid, shifuBid, followUpDetailLoadErrorMessage],
  );

  useEffect(() => {
    detailCacheRef.current.clear();
  }, [shifuBid]);

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
    fetchFollowUps(pageIndex, filters);
  }, [fetchFollowUps, filters, isGuest, isInitialized, pageIndex]);

  useEffect(() => {
    if (
      !isInitialized ||
      isGuest ||
      !detailOpen ||
      !selectedGeneratedBlockBid.trim()
    ) {
      return;
    }
    fetchFollowUpDetail();
  }, [
    detailOpen,
    fetchFollowUpDetail,
    isGuest,
    isInitialized,
    selectedGeneratedBlockBid,
  ]);

  const rows = useMemo(() => followUps.items || [], [followUps.items]);
  const currentPage = followUps.page || 1;
  const pageCount = Math.max(followUps.page_count || 0, 1);
  const hasChapterHierarchy = useMemo(
    () => resolveHasChapterHierarchy(rows),
    [rows],
  );
  const outlineFilterLabel = hasChapterHierarchy
    ? t('module.dashboard.detail.followUps.filters.chapterKeyword')
    : t('module.dashboard.detail.followUps.filters.lessonKeyword');
  const outlineFilterPlaceholder = hasChapterHierarchy
    ? t('module.dashboard.detail.followUps.filters.chapterKeywordPlaceholder')
    : t('module.dashboard.detail.followUps.filters.lessonKeywordPlaceholder');
  const outlineColumnLabel = hasChapterHierarchy
    ? t('module.dashboard.detail.followUps.table.chapter')
    : t('module.dashboard.detail.followUps.table.lesson');
  const summaryCards = useMemo(
    () => [
      {
        key: 'followUpCount',
        label: t('module.dashboard.detail.followUps.summary.followUpCount'),
        value: String(followUps.summary.follow_up_count || 0),
        tone: 'value' as const,
      },
      {
        key: 'userCount',
        label: t('module.dashboard.detail.followUps.summary.userCount'),
        value: String(followUps.summary.user_count || 0),
        tone: 'value' as const,
      },
      {
        key: 'lessonCount',
        label: t('module.dashboard.detail.followUps.summary.lessonCount'),
        value: String(followUps.summary.lesson_count || 0),
        tone: 'value' as const,
      },
      {
        key: 'latestFollowUpAt',
        label: t('module.dashboard.detail.followUps.summary.latestFollowUpAt'),
        value: formatDisplayValue(
          formatAdminUtcDateTime(followUps.summary.latest_follow_up_at),
          emptyValue,
        ),
        tone: 'timestamp' as const,
      },
    ],
    [emptyValue, followUps.summary, t],
  );

  const resolveUserSecondary = useCallback(
    (item: DashboardCourseFollowUpItem) =>
      item.nickname?.trim() || defaultUserName,
    [defaultUserName],
  );

  const handleSearch = useCallback(() => {
    const nextFilters = {
      userBid: filtersDraft.userBid,
      keyword: filtersDraft.keyword.trim(),
      chapterKeyword: filtersDraft.chapterKeyword.trim(),
      sourceStatus: filtersDraft.sourceStatus.trim(),
      startTime: filtersDraft.startTime,
      endTime: filtersDraft.endTime,
    };
    setFilters(nextFilters);
    setPageIndex(1);
  }, [filtersDraft]);

  const handleReset = useCallback(() => {
    const nextFilters = createFollowUpFilters();
    setFiltersDraft(nextFilters);
    setFilters(nextFilters);
    setPageIndex(1);
  }, []);

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
      setDetail(
        detailCacheRef.current.get(normalizedGeneratedBlockBid) ?? null,
      );
      setDetailError(null);
      setDetailLoading(
        !detailCacheRef.current.has(normalizedGeneratedBlockBid),
      );
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
  const sourceStatusOptions = useMemo(
    () => [
      {
        value: ALL_SOURCE_STATUS,
        label: t('module.dashboard.detail.followUps.filters.sourceStatusAll'),
      },
      {
        value: 'resolved',
        label: t(
          'module.dashboard.detail.followUps.filters.sourceStatusResolved',
        ),
      },
      {
        value: 'missing',
        label: t(
          'module.dashboard.detail.followUps.filters.sourceStatusMissing',
        ),
      },
    ],
    [t],
  );
  const detailSheetLabels = useMemo<FollowUpDetailSheetLabels>(
    () => ({
      title: t('module.dashboard.detail.followUps.drawer.title'),
      basicInfoSection: t(
        'module.dashboard.detail.followUps.drawer.sections.basicInfo',
      ),
      currentRecordSection: t(
        'module.dashboard.detail.followUps.drawer.sections.currentRecord',
      ),
      currentRecordHint: t(
        'module.dashboard.detail.followUps.drawer.currentRecordHint',
      ),
      timelineSection: t(
        'module.dashboard.detail.followUps.drawer.sections.timeline',
      ),
      user: t('module.dashboard.detail.followUps.drawer.fields.user'),
      nickname: t('module.dashboard.detail.followUps.drawer.fields.nickname'),
      followUpTime: t(
        'module.dashboard.detail.followUps.drawer.fields.followUpTime',
      ),
      turnIndex: t('module.dashboard.detail.followUps.drawer.fields.turnIndex'),
      turnIndexHelp: t('module.dashboard.detail.followUps.turnIndexHelp'),
      currentFollowUp: t(
        'module.dashboard.detail.followUps.drawer.fields.currentFollowUp',
      ),
      currentAnswer: t(
        'module.dashboard.detail.followUps.drawer.fields.currentAnswer',
      ),
      timelineCurrent: t(
        'module.dashboard.detail.followUps.drawer.timeline.current',
      ),
    }),
    [t],
  );
  const resolveDetailOutlineFieldLabel = useCallback(
    () => t('module.dashboard.detail.followUps.drawer.fields.lesson'),
    [t],
  );
  const formatDetailTurnIndex = useCallback(
    (turnIndex: number | null | undefined) =>
      turnIndex == null
        ? emptyValue
        : t('module.dashboard.detail.followUps.turnIndex', {
            count: turnIndex,
          }),
    [emptyValue, t],
  );
  const resolveDetailRoleLabel = useCallback(
    (role: string) =>
      role === 'teacher'
        ? t('module.dashboard.detail.followUps.drawer.timeline.teacher')
        : t('module.dashboard.detail.followUps.drawer.timeline.student'),
    [t],
  );
  const userFilterDisplayValue = filtersDraft.userBid || filtersDraft.keyword;
  const filterItems: AdminFilterItem[] = [
    createTextFilterItem({
      key: 'user_bid',
      label: t('module.dashboard.detail.followUps.filters.userKeyword'),
      value: userFilterDisplayValue,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          keyword: value,
          userBid:
            previous.userBid && value.trim() === previous.userBid.trim()
              ? previous.userBid
              : '',
        })),
      onSubmit: handleSearch,
      placeholder: userKeywordPlaceholder,
      clearLabel,
      labelClassName: DASHBOARD_FILTER_LABEL_STANDARD_CLASS,
      contentClassName: DASHBOARD_FILTER_TEXT_CONTENT_LEAD_CLASS,
      inputClassName: 'min-w-0',
    }),
    createTextFilterItem({
      key: 'chapter_keyword',
      label: outlineFilterLabel,
      value: filtersDraft.chapterKeyword,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          chapterKeyword: value,
        })),
      onSubmit: handleSearch,
      placeholder: outlineFilterPlaceholder,
      clearLabel,
      labelClassName: DASHBOARD_FILTER_LABEL_STANDARD_CLASS,
      contentClassName: DASHBOARD_FILTER_TEXT_CONTENT_BALANCED_CLASS,
      inputClassName: 'min-w-0',
    }),
    createSelectFilterItem({
      key: 'source_status',
      label: t('module.dashboard.detail.followUps.filters.sourceStatus'),
      labelId: FOLLOW_UP_SOURCE_STATUS_LABEL_ID,
      value: filtersDraft.sourceStatus,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          sourceStatus: value,
        })),
      triggerId: FOLLOW_UP_SOURCE_STATUS_TRIGGER_ID,
      triggerAriaLabelledBy: FOLLOW_UP_SOURCE_STATUS_LABEL_ID,
      placeholder: t(
        'module.dashboard.detail.followUps.filters.sourceStatusAll',
      ),
      options: sourceStatusOptions,
      contentClassName: DASHBOARD_FILTER_SELECT_CONTENT_CLASS,
      triggerClassName: 'min-w-[140px]',
    }),
    createDateRangeFilterItem({
      key: 'date_range',
      label: t('module.dashboard.detail.followUps.filters.followUpTime'),
      startValue: filtersDraft.startTime,
      endValue: filtersDraft.endTime,
      triggerAriaLabel: t(
        'module.dashboard.detail.followUps.filters.followUpTime',
      ),
      onChange: ({ start, end }) =>
        setFiltersDraft(previous => ({
          ...previous,
          startTime: start,
          endTime: end,
        })),
      placeholder: t(
        'module.dashboard.detail.followUps.filters.timePlaceholder',
      ),
      resetLabel: t('module.dashboard.detail.followUps.filters.reset'),
      clearLabel,
    }),
  ];

  if (!isInitialized || isGuest) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Loading />
      </div>
    );
  }

  return (
    <div className='h-full overflow-auto pr-1'>
      <div className='pb-6'>
        <AdminTitle title={t('module.dashboard.detail.followUps.title')} />
        <div className='space-y-5'>
          <CourseFeedbackSummaryCards
            cards={summaryCards}
            gridClassName={DASHBOARD_DETAIL_SUMMARY_GRID_CLASS}
            size='compact'
          />

          <Card className='overflow-hidden border-border/80 shadow-sm'>
            <CardHeader className='pb-3'>
              <div className='space-y-0.5'>
                <CardTitle className='text-base font-semibold tracking-normal'>
                  {t('module.dashboard.detail.followUps.table.title')}
                </CardTitle>
                <p className='text-xs leading-5 text-muted-foreground/85'>
                  {t('module.dashboard.detail.followUps.summary.scopeHint')}
                </p>
                <p className='text-xs leading-5 text-muted-foreground/85'>
                  {t('module.dashboard.detail.followUps.turnIndexHelp')}
                </p>
              </div>
            </CardHeader>
            <CardContent className='space-y-5 pt-0'>
              <div className={DASHBOARD_FILTER_PANEL_CLASS}>
                <AdminFilter
                  items={filterItems}
                  expanded={false}
                  onExpandedChange={() => undefined}
                  onReset={handleReset}
                  onSearch={handleSearch}
                  actionsDisabled={loading}
                  showActions={false}
                  resetLabel={t(
                    'module.dashboard.detail.followUps.filters.reset',
                  )}
                  searchLabel={t(
                    'module.dashboard.detail.followUps.filters.search',
                  )}
                  expandLabel={t('common.core.expand')}
                  collapseLabel={t('common.core.collapse')}
                  collapsedCount={4}
                  showToggle={false}
                  labelClassName={DASHBOARD_FILTER_LABEL_CLASS}
                  contentClassName={DASHBOARD_FILTER_CONTENT_CLASS}
                  collapsedGridClassName={
                    DASHBOARD_FILTER_FOLLOW_UPS_GRID_CLASS
                  }
                  expandedGridClassName={DASHBOARD_FILTER_FOLLOW_UPS_GRID_CLASS}
                />
                <div className={DASHBOARD_FILTER_FOOTER_CLASS}>
                  <div className={DASHBOARD_FILTER_RESULT_COUNT_CLASS}>
                    {t(
                      'module.dashboard.detail.followUps.filters.resultCount',
                      {
                        count: followUps.total,
                      },
                    )}
                  </div>
                  <div className={DASHBOARD_FILTER_ACTIONS_CLASS}>
                    <Button
                      type='button'
                      size='sm'
                      variant='outline'
                      className={DASHBOARD_FILTER_ACTION_BUTTON_CLASS}
                      onClick={handleReset}
                      disabled={loading}
                    >
                      {t('module.dashboard.detail.followUps.filters.reset')}
                    </Button>
                    <Button
                      type='button'
                      size='sm'
                      className={DASHBOARD_FILTER_ACTION_BUTTON_CLASS}
                      onClick={handleSearch}
                      disabled={loading}
                    >
                      {t('module.dashboard.detail.followUps.filters.search')}
                    </Button>
                  </div>
                </div>
              </div>

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
                  emptyContent={t(
                    'module.dashboard.detail.followUps.table.empty',
                  )}
                  emptyColSpan={6}
                  withTooltipProvider
                  tableWrapperClassName='overflow-auto'
                  loadingClassName='min-h-[240px]'
                  table={emptyRow => (
                    <Table className='table-auto'>
                      <TableHeader>
                        <TableRow>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-xs text-left'>
                            {t(
                              'module.dashboard.detail.followUps.table.createdAt',
                            )}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-xs text-left'>
                            {t('module.dashboard.detail.followUps.table.user')}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-xs text-left'>
                            {outlineColumnLabel}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-xs text-left'>
                            {t(
                              'module.dashboard.detail.followUps.table.content',
                            )}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-xs text-left'>
                            {t(
                              'module.dashboard.detail.followUps.table.turnIndex',
                            )}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-xs text-left'>
                            {t(
                              'module.dashboard.detail.followUps.table.action',
                            )}
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
                                ? t(
                                    'module.dashboard.detail.followUps.turnIndex',
                                    {
                                      count: item.turn_index,
                                    },
                                  )
                                : emptyValue;
                              return (
                                <TableRow key={item.generated_block_bid}>
                                  <TableCell className='whitespace-nowrap py-3 align-middle text-sm text-foreground/80'>
                                    <AdminTooltipText
                                      text={formatAdminUtcDateTime(
                                        item.created_at,
                                      )}
                                      emptyValue={emptyValue}
                                      className='block max-w-[180px]'
                                    />
                                  </TableCell>
                                  <TableCell className='py-3 align-middle'>
                                    <StackedTooltipText
                                      primary={primaryAccount}
                                      primaryEmptyValue={emptyValue}
                                      primaryClassName='block max-w-[180px] text-sm text-foreground'
                                      secondary={secondaryAccount}
                                      secondaryEmptyValue={emptyValue}
                                      secondaryClassName='block max-w-[180px] text-xs text-muted-foreground'
                                      wrapSecondary
                                    />
                                  </TableCell>
                                  <TableCell className='py-3 align-top'>
                                    <StackedTooltipText
                                      primary={primaryLessonDisplay}
                                      primaryEmptyValue={emptyValue}
                                      primaryClassName='block max-w-[220px] text-sm text-foreground'
                                      secondary={secondaryChapterDisplay}
                                      secondaryEmptyValue={emptyValue}
                                      secondaryClassName='block max-w-[220px] text-xs text-muted-foreground'
                                    />
                                  </TableCell>
                                  <TableCell className='py-3 align-top'>
                                    <div className='py-1.5'>
                                      <AdminTooltipText
                                        text={item.follow_up_content}
                                        emptyValue={emptyValue}
                                        className='block max-w-[320px] text-sm font-medium text-foreground'
                                      />
                                      <div className='mt-2'>
                                        <FollowUpSourceStatusBadge
                                          hasSourceOutput={
                                            item.has_source_output
                                          }
                                          resolvedLabel={t(
                                            'module.dashboard.detail.followUps.table.sourceResolved',
                                          )}
                                          missingLabel={t(
                                            'module.dashboard.detail.followUps.table.sourceMissing',
                                          )}
                                        />
                                      </div>
                                    </div>
                                  </TableCell>
                                  <TableCell className='whitespace-nowrap py-3 align-top text-sm text-foreground'>
                                    {turnIndexLabel}
                                  </TableCell>
                                  <TableCell className='py-3 align-top'>
                                    <Button
                                      type='button'
                                      variant='link'
                                      className='h-auto px-0 py-0 text-left text-sm'
                                      onClick={() =>
                                        handleOpenDetail(
                                          item.generated_block_bid,
                                        )
                                      }
                                    >
                                      {t(
                                        'module.dashboard.detail.followUps.table.detailAction',
                                      )}
                                    </Button>
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                      </TableBody>
                    </Table>
                  )}
                  footer={
                    <AdminPagination
                      pageIndex={currentPage}
                      pageCount={pageCount}
                      onPageChange={handlePageChange}
                      prevLabel={t('module.dashboard.pagination.prev')}
                      nextLabel={t('module.dashboard.pagination.next')}
                      prevAriaLabel={t('module.dashboard.pagination.prev')}
                      nextAriaLabel={t('module.dashboard.pagination.next')}
                      className='mx-0 w-auto justify-end'
                      hideWhenSinglePage
                    />
                  }
                />
              )}
            </CardContent>
          </Card>
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
        onRetry={() => fetchFollowUpDetail({ forceRefresh: true })}
        onOpenChange={handleDetailOpenChange}
      />
    </div>
  );
}
