'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminFilter, {
  type AdminFilterItem,
} from '@/app/admin/components/AdminFilter';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  createDateRangeFilterItem,
  createSelectFilterItem,
  createTextFilterItem,
} from '@/app/admin/components/adminFilterFieldBuilders';
import { useEnvStore } from '@/c-store';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
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
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { cn } from '@/lib/utils';
import { useUserStore } from '@/store';
import type {
  DashboardCourseFollowUpDetailResponse,
  DashboardCourseFollowUpItem,
  DashboardCourseFollowUpListResponse,
} from '@/types/dashboard';
import {
  DASHBOARD_FILTER_CONTENT_CLASS,
  DASHBOARD_FILTER_LABEL_CLASS,
} from '../../dashboardFilterUiShared';
import { buildAdminDashboardCourseDetailUrl } from '../../admin-dashboard-routes';
import FollowUpDetailSheet from './FollowUpDetailSheet';

type ErrorState = { message: string; code?: number };
type ContactMode = 'phone' | 'email';

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
const FOLLOW_UP_FILTER_GRID_CLASS =
  'gap-x-5 xl:grid-cols-[minmax(0,300px)_minmax(0,300px)_minmax(0,200px)_minmax(0,280px)]';
const FOLLOW_UP_FILTER_LABEL_CLASS = 'w-[68px]';

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

const formatValue = (value: string | undefined | null, emptyValue: string) => {
  const normalizedValue = value?.trim() || '';
  return normalizedValue || emptyValue;
};

const resolvePrimaryLessonDisplay = ({
  lessonTitle,
  chapterTitle,
  emptyValue,
}: {
  lessonTitle?: string;
  chapterTitle?: string;
  emptyValue: string;
}) => formatValue(lessonTitle || chapterTitle, emptyValue);

const resolveSecondaryChapterDisplay = ({
  chapterTitle,
  lessonTitle,
}: {
  chapterTitle?: string;
  lessonTitle?: string;
}) => {
  const normalizedChapterTitle = chapterTitle?.trim() || '';
  const normalizedLessonTitle = lessonTitle?.trim() || '';
  if (
    !normalizedChapterTitle ||
    normalizedChapterTitle === normalizedLessonTitle
  ) {
    return '';
  }
  return normalizedChapterTitle;
};

const resolvePrimaryAccount = ({
  mobile,
  email,
  userBid,
  contactMode,
  emptyValue,
}: {
  mobile?: string;
  email?: string;
  userBid?: string;
  contactMode: ContactMode;
  emptyValue: string;
}) => {
  const preferred = contactMode === 'email' ? email : mobile;
  const alternate = contactMode === 'email' ? mobile : email;
  return formatValue(preferred || alternate || userBid, emptyValue);
};

const splitTimestampValue = (value: string) => {
  const normalizedValue = value
    .replace(/[,.\u202F]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!normalizedValue) {
    return [];
  }

  const [datePart, timePart, ...rest] = normalizedValue.split(' ');
  if (!timePart || rest.length > 0) {
    return [normalizedValue];
  }

  return [datePart, timePart];
};

export default function AdminDashboardCourseFollowUpsPage() {
  const { t } = useTranslation();
  const params = useParams<{ shifu_bid?: string }>();
  const searchParams = useSearchParams();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);
  const timezone = getBrowserTimeZone();

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = '--';
  const clearLabel = t('common.core.close');
  const unknownErrorMessage = t('common.core.unknownError');
  const defaultUserName = t('module.user.defaultUserName');
  const contactMode = useMemo<ContactMode>(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const detailPageUrl = useMemo(
    () => buildAdminDashboardCourseDetailUrl(shifuBid),
    [shifuBid],
  );
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
      contactMode === 'email'
        ? t(
            'module.dashboard.detail.followUps.filters.userKeywordPlaceholderEmail',
          )
        : t(
            'module.dashboard.detail.followUps.filters.userKeywordPlaceholderPhone',
          ),
    [contactMode, t],
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
        setError({ message: unknownErrorMessage });
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
          ...(timezone ? { timezone } : {}),
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
        if (err instanceof ErrorWithCode) {
          setError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setError({ message: err.message });
        } else {
          setError({ message: unknownErrorMessage });
        }
      } finally {
        if (requestId === listRequestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [filters, shifuBid, timezone, unknownErrorMessage],
  );

  const fetchFollowUpDetail = useCallback(
    async ({ forceRefresh = false }: { forceRefresh?: boolean } = {}) => {
      if (!shifuBid.trim() || !selectedGeneratedBlockBid.trim()) {
        setDetailError({ message: unknownErrorMessage });
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
          ...(timezone ? { timezone } : {}),
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
        if (err instanceof ErrorWithCode) {
          setDetailError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setDetailError({ message: err.message });
        } else {
          setDetailError({ message: unknownErrorMessage });
        }
      } finally {
        if (requestId === detailRequestIdRef.current) {
          setDetailLoading(false);
        }
      }
    },
    [selectedGeneratedBlockBid, shifuBid, timezone, unknownErrorMessage],
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
    () =>
      rows.some(item => {
        const chapterTitle = item.chapter_title?.trim() || '';
        const lessonTitle = item.lesson_title?.trim() || '';
        return !!chapterTitle && !!lessonTitle && chapterTitle !== lessonTitle;
      }),
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
        label: t('module.dashboard.detail.followUps.summary.followUpCount'),
        value: String(followUps.summary.follow_up_count || 0),
        tone: 'default' as const,
      },
      {
        label: t('module.dashboard.detail.followUps.summary.userCount'),
        value: String(followUps.summary.user_count || 0),
        tone: 'default' as const,
      },
      {
        label: t('module.dashboard.detail.followUps.summary.lessonCount'),
        value: String(followUps.summary.lesson_count || 0),
        tone: 'default' as const,
      },
      {
        label: t('module.dashboard.detail.followUps.summary.latestFollowUpAt'),
        value: formatValue(followUps.summary.latest_follow_up_at, emptyValue),
        tone: 'timestamp' as const,
      },
    ],
    [emptyValue, followUps.summary, t],
  );

  const resolveUserSecondary = useCallback(
    (item: DashboardCourseFollowUpItem) => {
      const nickname = item.nickname?.trim() || '';
      if (!nickname || nickname === defaultUserName) {
        return '';
      }
      return nickname;
    },
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
        setDetailError({ message: unknownErrorMessage });
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
    [unknownErrorMessage],
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
  const filterItems: AdminFilterItem[] = [
    createTextFilterItem({
      key: 'user_bid',
      label: t('module.dashboard.detail.followUps.filters.userKeyword'),
      value: filtersDraft.keyword,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          keyword: value,
          userBid:
            previous.userBid && value.trim() !== previous.keyword.trim()
              ? ''
              : previous.userBid,
        })),
      onSubmit: handleSearch,
      placeholder: userKeywordPlaceholder,
      clearLabel,
      labelClassName: FOLLOW_UP_FILTER_LABEL_CLASS,
      contentClassName: 'min-w-0 flex-[1.35]',
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
      labelClassName: FOLLOW_UP_FILTER_LABEL_CLASS,
      contentClassName: 'min-w-0 flex-[1.15]',
      inputClassName: 'min-w-0',
    }),
    createSelectFilterItem({
      key: 'source_status',
      label: t('module.dashboard.detail.followUps.filters.sourceStatus'),
      value: filtersDraft.sourceStatus,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          sourceStatus: value,
        })),
      placeholder: t(
        'module.dashboard.detail.followUps.filters.sourceStatusAll',
      ),
      options: sourceStatusOptions,
      contentClassName: 'min-w-0 flex-[1.1]',
      triggerClassName: 'min-w-[140px]',
    }),
    createDateRangeFilterItem({
      key: 'date_range',
      label: t('module.dashboard.detail.followUps.filters.followUpTime'),
      startValue: filtersDraft.startTime,
      endValue: filtersDraft.endTime,
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
        <AdminBreadcrumb
          items={[
            {
              label: t('module.dashboard.title'),
              href: '/admin/dashboard',
            },
            {
              label: t('module.dashboard.detail.title'),
              href: detailPageUrl || '/admin/dashboard',
            },
            { label: t('module.dashboard.detail.followUps.title') },
          ]}
        />
        <div className='space-y-5'>
          <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
            {summaryCards.map(card => (
              <Card
                key={card.label}
                className='border-border/80 shadow-sm'
              >
                <CardContent className='flex h-full flex-col p-4'>
                  <div className='text-sm font-medium text-muted-foreground'>
                    {card.label}
                  </div>
                  {card.tone === 'timestamp' ? (
                    <div className='mt-3 space-y-0.5 text-foreground'>
                      {splitTimestampValue(card.value).map((part, index) => (
                        <div
                          key={`${card.label}-${part}-${index}`}
                          className={cn(
                            'break-all tracking-tight',
                            index === 0 ? 'text-base font-medium' : 'text-sm',
                          )}
                        >
                          {part}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className='mt-3 text-xl font-semibold text-foreground'>
                      {card.value}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

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
              <div className='rounded-xl border border-border bg-muted/20 p-3'>
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
                  collapsedGridClassName={FOLLOW_UP_FILTER_GRID_CLASS}
                  expandedGridClassName={FOLLOW_UP_FILTER_GRID_CLASS}
                />
                <div className='mt-3 flex flex-col gap-3 pl-3 sm:flex-row sm:items-center sm:justify-between'>
                  <div className='text-sm text-muted-foreground'>
                    {t(
                      'module.dashboard.detail.followUps.filters.resultCount',
                      {
                        count: followUps.total,
                      },
                    )}
                  </div>
                  <div className='flex items-center justify-end gap-2'>
                    <Button
                      type='button'
                      size='sm'
                      variant='outline'
                      className='h-9 px-4'
                      onClick={handleReset}
                      disabled={loading}
                    >
                      {t('module.dashboard.detail.followUps.filters.reset')}
                    </Button>
                    <Button
                      type='button'
                      size='sm'
                      className='h-9 px-4'
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
                                contactMode,
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
                                      text={item.created_at}
                                      emptyValue={emptyValue}
                                      className='block max-w-[180px]'
                                    />
                                  </TableCell>
                                  <TableCell className='py-3 align-middle'>
                                    <div className='flex flex-col gap-0.5 leading-tight'>
                                      <div className='font-medium text-foreground'>
                                        <AdminTooltipText
                                          text={primaryAccount}
                                          emptyValue={emptyValue}
                                          className='block max-w-[180px] text-sm text-foreground'
                                        />
                                      </div>
                                      {secondaryAccount ? (
                                        <div className='text-xs text-muted-foreground'>
                                          <AdminTooltipText
                                            text={secondaryAccount}
                                            emptyValue={emptyValue}
                                            className='block max-w-[180px] text-xs text-muted-foreground'
                                          />
                                        </div>
                                      ) : null}
                                    </div>
                                  </TableCell>
                                  <TableCell className='py-3 align-top'>
                                    <div className='flex flex-col gap-0.5 leading-tight'>
                                      <div className='font-medium text-foreground'>
                                        <AdminTooltipText
                                          text={primaryLessonDisplay}
                                          emptyValue={emptyValue}
                                          className='block max-w-[220px] text-sm text-foreground'
                                        />
                                      </div>
                                      {secondaryChapterDisplay ? (
                                        <AdminTooltipText
                                          text={secondaryChapterDisplay}
                                          emptyValue={emptyValue}
                                          className='block max-w-[220px] text-xs text-muted-foreground'
                                        />
                                      ) : null}
                                    </div>
                                  </TableCell>
                                  <TableCell className='py-3 align-top'>
                                    <div className='py-1.5'>
                                      <AdminTooltipText
                                        text={item.follow_up_content}
                                        emptyValue={emptyValue}
                                        className='block max-w-[320px] text-sm font-medium text-foreground'
                                      />
                                      <div className='mt-2'>
                                        <Badge
                                          variant='outline'
                                          className={cn(
                                            'border px-2 py-0.5 text-[11px] font-medium',
                                            item.has_source_output
                                              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                                              : 'border-amber-200 bg-amber-50 text-amber-700',
                                          )}
                                        >
                                          {item.has_source_output
                                            ? t(
                                                'module.dashboard.detail.followUps.table.sourceResolved',
                                              )
                                            : t(
                                                'module.dashboard.detail.followUps.table.sourceMissing',
                                              )}
                                        </Badge>
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
        contactMode={contactMode}
        defaultUserName={defaultUserName}
        resolveLessonDisplay={resolvePrimaryLessonDisplay}
        onRetry={() => fetchFollowUpDetail({ forceRefresh: true })}
        onOpenChange={handleDetailOpenChange}
      />
    </div>
  );
}
