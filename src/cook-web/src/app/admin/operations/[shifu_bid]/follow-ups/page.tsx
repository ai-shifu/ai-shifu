'use client';

import { X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
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
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { cn } from '@/lib/utils';
import {
  buildAdminOperationsCourseDetailUrl,
  buildAdminOperationsCourseFollowUpsUrl,
} from '../../operation-course-routes';
import type {
  AdminOperationCourseFollowUpDetailResponse,
  AdminOperationCourseFollowUpItem,
  AdminOperationCourseFollowUpListResponse,
} from '../../operation-course-types';
import useOperatorGuard from '../../useOperatorGuard';
import FollowUpDetailSheet from './FollowUpDetailSheet';

type ErrorState = { message: string; code?: number };
type ContactMode = 'phone' | 'email';

type FollowUpFilters = {
  keyword: string;
  chapterKeyword: string;
  startTime: string;
  endTime: string;
};

const PAGE_SIZE = 20;
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
  startTime: '',
  endTime: '',
});

const formatCount = (value: number): string =>
  Number.isFinite(value) ? value.toLocaleString() : '--';

const formatValue = (value: string | undefined | null, emptyValue: string) => {
  const normalizedValue = value?.trim() || '';
  return normalizedValue || emptyValue;
};

const splitTimestampValue = (value: string) => {
  const normalizedValue = value
    .replace(/[,\u202F]+/g, ' ')
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
  emptyValue,
}: {
  chapterTitle?: string;
  lessonTitle?: string;
  emptyValue: string;
}) => {
  const normalizedChapterTitle = chapterTitle?.trim() || '';
  const normalizedLessonTitle = lessonTitle?.trim() || '';
  if (
    !normalizedChapterTitle ||
    normalizedChapterTitle === normalizedLessonTitle
  ) {
    return '';
  }
  return formatValue(normalizedChapterTitle, emptyValue);
};

const resolveDetailLessonDisplay = ({
  lessonTitle,
  chapterTitle,
  emptyValue,
}: {
  lessonTitle?: string;
  chapterTitle?: string;
  emptyValue: string;
}) => formatValue(lessonTitle || chapterTitle, emptyValue);

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

function ClearableTextInput({
  id,
  value,
  placeholder,
  clearLabel,
  onChange,
  onSubmit,
}: {
  id?: string;
  value: string;
  placeholder: string;
  clearLabel: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const hasValue = value.trim().length > 0;

  return (
    <div className='relative'>
      <Input
        id={id}
        value={value}
        onChange={event => onChange(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter') {
            event.preventDefault();
            onSubmit();
          }
        }}
        placeholder={placeholder}
        className={cn('h-9', hasValue && 'pr-9')}
      />
      {hasValue ? (
        <button
          type='button'
          aria-label={clearLabel}
          className='absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground'
          onMouseDown={event => event.preventDefault()}
          onClick={() => onChange('')}
        >
          <X className='h-3.5 w-3.5' />
        </button>
      ) : null}
    </div>
  );
}

/**
 * t('module.operationsCourse.detail.followUps.back')
 * t('module.operationsCourse.detail.followUps.title')
 * t('module.operationsCourse.detail.followUps.openMetric')
 * t('module.operationsCourse.detail.followUps.summary.followUpCount')
 * t('module.operationsCourse.detail.followUps.summary.userCount')
 * t('module.operationsCourse.detail.followUps.summary.lessonCount')
 * t('module.operationsCourse.detail.followUps.summary.latestFollowUpAt')
 * t('module.operationsCourse.detail.followUps.summary.scopeHint')
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
 * t('module.operationsCourse.detail.followUps.filters.timeRangePlaceholder')
 * t('module.operationsCourse.detail.followUps.filters.search')
 * t('module.operationsCourse.detail.followUps.filters.reset')
 * t('module.operationsCourse.detail.followUps.table.title')
 * t('module.operationsCourse.detail.followUps.table.createdAt')
 * t('module.operationsCourse.detail.followUps.table.user')
 * t('module.operationsCourse.detail.followUps.table.chapter')
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
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');
  const { isReady } = useOperatorGuard();
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = tOperations('detail.followUps.emptyValue');
  const clearLabel = t('common.core.close');
  const unknownErrorMessage = t('common.core.unknownError');
  const defaultUserName = t('module.user.defaultUserName');
  const contactMode = useMemo<ContactMode>(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
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
      contactMode === 'email'
        ? tOperations('detail.followUps.filters.userKeywordPlaceholderEmail')
        : tOperations('detail.followUps.filters.userKeywordPlaceholderPhone'),
    [contactMode, tOperations],
  );

  const [followUps, setFollowUps] =
    useState<AdminOperationCourseFollowUpListResponse>(
      EMPTY_FOLLOW_UPS_RESPONSE,
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
        const response = (await api.getAdminOperationCourseFollowUps({
          shifu_bid: shifuBid,
          page: targetPage,
          page_size: PAGE_SIZE,
          keyword: resolvedFilters.keyword.trim(),
          chapter_keyword: resolvedFilters.chapterKeyword.trim(),
          start_time: resolvedFilters.startTime,
          end_time: resolvedFilters.endTime,
        })) as AdminOperationCourseFollowUpListResponse;
        if (requestId !== listRequestIdRef.current) {
          return;
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
    [filters, shifuBid, unknownErrorMessage],
  );

  const fetchFollowUpDetail = useCallback(async () => {
    if (!shifuBid.trim() || !selectedGeneratedBlockBid.trim()) {
      setDetailError({ message: unknownErrorMessage });
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
  }, [selectedGeneratedBlockBid, shifuBid, unknownErrorMessage]);

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
    () =>
      rows.some(item => {
        const chapterTitle = item.chapter_title?.trim() || '';
        const lessonTitle = item.lesson_title?.trim() || '';
        return !!chapterTitle && !!lessonTitle && chapterTitle !== lessonTitle;
      }),
    [rows],
  );
  const outlineFilterLabel = hasChapterHierarchy
    ? tOperations('detail.followUps.filters.chapterKeyword')
    : tOperations('detail.followUps.filters.lessonKeyword');
  const outlineFilterPlaceholder = hasChapterHierarchy
    ? tOperations('detail.followUps.filters.chapterKeywordPlaceholder')
    : tOperations('detail.followUps.filters.lessonKeywordPlaceholder');
  const outlineColumnLabel = hasChapterHierarchy
    ? tOperations('detail.followUps.table.chapter')
    : tOperations('detail.followUps.table.lesson');
  const summaryScopeHint = tOperations('detail.followUps.summary.scopeHint');
  const turnIndexHelpText = tOperations('detail.followUps.turnIndexHelp');
  const userKeywordInputId = 'follow-up-user-keyword-filter';
  const outlineKeywordInputId = 'follow-up-outline-keyword-filter';
  const followUpTimeFilterAriaLabel = tOperations(
    'detail.followUps.filters.followUpTime',
  );
  const summaryCards = useMemo(
    () => [
      {
        key: 'followUpCount',
        label: tOperations('detail.followUps.summary.followUpCount'),
        value: formatCount(followUps.summary.follow_up_count),
        tone: 'number' as const,
      },
      {
        key: 'userCount',
        label: tOperations('detail.followUps.summary.userCount'),
        value: formatCount(followUps.summary.user_count),
        tone: 'number' as const,
      },
      {
        key: 'lessonCount',
        label: tOperations('detail.followUps.summary.lessonCount'),
        value: formatCount(followUps.summary.lesson_count),
        tone: 'number' as const,
      },
      {
        key: 'latestFollowUpAt',
        label: tOperations('detail.followUps.summary.latestFollowUpAt'),
        value:
          formatAdminUtcDateTime(followUps.summary.latest_follow_up_at) ||
          emptyValue,
        tone: 'timestamp' as const,
      },
    ],
    [emptyValue, followUps.summary, tOperations],
  );

  const resolveUserSecondary = useCallback(
    (item: AdminOperationCourseFollowUpItem) => {
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
      keyword: filtersDraft.keyword.trim(),
      chapterKeyword: filtersDraft.chapterKeyword.trim(),
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
      setDetail(null);
      setDetailError(null);
      setDetailLoading(true);
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
          errorMessage={unknownErrorMessage}
          onRetry={() => router.push('/admin/operations')}
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
              {tOperations('detail.followUps.title')}
            </h1>
            <p className='text-sm text-muted-foreground'>{summaryScopeHint}</p>
            <AdminTimezoneHint
              namespace='module.operationsCourse'
              textKey='timezoneHint'
            />
          </div>
          <Button
            variant='outline'
            className='sm:mr-3'
            onClick={() => {
              if (detailPageUrl) {
                router.push(detailPageUrl);
              }
            }}
          >
            {tOperations('detail.followUps.back')}
          </Button>
        </div>

        <div className='min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain pr-1'>
          <div className='space-y-5 pb-6'>
            <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
              {summaryCards.map(card => (
                <Card
                  key={card.key}
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
                            key={`${card.key}-${part}-${index}`}
                            className={cn(
                              'break-all tracking-tight',
                              index === 0 ? 'text-lg font-medium' : 'text-base',
                            )}
                          >
                            {part}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className='mt-3 text-2xl font-semibold text-foreground'>
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
                    {tOperations('detail.followUps.table.title')}
                  </CardTitle>
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
                  <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
                    <div className='flex flex-col gap-2'>
                      <label
                        htmlFor={userKeywordInputId}
                        className='text-xs font-medium text-muted-foreground'
                      >
                        {tOperations('detail.followUps.filters.userKeyword')}
                      </label>
                      <ClearableTextInput
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
                      <ClearableTextInput
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
                      <label className='text-xs font-medium text-muted-foreground'>
                        {tOperations('detail.followUps.filters.followUpTime')}
                      </label>
                      <AdminDateRangeFilter
                        startValue={filtersDraft.startTime}
                        endValue={filtersDraft.endTime}
                        triggerAriaLabel={followUpTimeFilterAriaLabel}
                        placeholder={tOperations(
                          'detail.followUps.filters.timeRangePlaceholder',
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

                  <div className='mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3 xl:items-end'>
                    <div className='pl-3 text-sm text-muted-foreground xl:self-center'>
                      {tOperations('detail.followUps.filters.resultCount', {
                        count: followUps.total,
                      })}
                    </div>
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
                    emptyColSpan={6}
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
                              {outlineColumnLabel}
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
                                    emptyValue,
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
                                      <div className='flex flex-col gap-0.5 leading-tight'>
                                        <div className='font-medium text-foreground'>
                                          <AdminTooltipText
                                            text={primaryAccount}
                                            emptyValue={emptyValue}
                                            className='mx-auto block max-w-full text-sm text-foreground'
                                          />
                                        </div>
                                        {secondaryAccount ? (
                                          <div className='text-xs text-muted-foreground'>
                                            <AdminTooltipText
                                              text={secondaryAccount}
                                              emptyValue={emptyValue}
                                              className='mx-auto block max-w-full text-xs text-muted-foreground'
                                            />
                                          </div>
                                        ) : null}
                                      </div>
                                    </TableCell>
                                    <TableCell
                                      className='border-r border-border py-3 text-center align-top last:border-r-0'
                                      style={getColumnStyle('lesson')}
                                    >
                                      <div className='flex flex-col gap-0.5 leading-tight'>
                                        <div className='font-medium text-foreground'>
                                          <AdminTooltipText
                                            text={primaryLessonDisplay}
                                            emptyValue={emptyValue}
                                            className='mx-auto block max-w-full text-sm text-foreground'
                                          />
                                        </div>
                                        {secondaryChapterDisplay ? (
                                          <AdminTooltipText
                                            text={secondaryChapterDisplay}
                                            emptyValue={emptyValue}
                                            className='mx-auto block max-w-full text-xs text-muted-foreground'
                                          />
                                        ) : null}
                                      </div>
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
                    footer={
                      <AdminPagination
                        pageIndex={currentPage}
                        pageCount={pageCount}
                        onPageChange={handlePageChange}
                        prevLabel={t('module.order.paginationPrev', 'Previous')}
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
                        hideWhenSinglePage
                      />
                    }
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
        contactMode={contactMode}
        defaultUserName={defaultUserName}
        resolveLessonDisplay={resolveDetailLessonDisplay}
        onRetry={fetchFollowUpDetail}
        onOpenChange={handleDetailOpenChange}
      />
    </div>
  );
}
