'use client';

import { ChevronDown, ChevronUp, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
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
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { cn } from '@/lib/utils';
import {
  buildAdminOperationsCourseDetailUrl,
  buildAdminOperationsCourseRatingsUrl,
} from '../../operation-course-routes';
import type {
  AdminOperationCourseRatingItem,
  AdminOperationCourseRatingListResponse,
} from '../../operation-course-types';
import useOperatorGuard from '../../useOperatorGuard';

type ErrorState = { message: string; code?: number };
type ContactMode = 'phone' | 'email';
type RatingCommentFilter = 'all' | 'commented';
type RatingModeFilter = 'all' | 'read' | 'listen';
type RatingSortBy = 'latest_desc' | 'score_asc';

type RatingFilters = {
  keyword: string;
  chapterKeyword: string;
  score: string;
  mode: RatingModeFilter;
  commentFilter: RatingCommentFilter;
  sortBy: RatingSortBy;
  startTime: string;
  endTime: string;
};

const PAGE_SIZE = 20;
const COLUMN_MIN_WIDTH = 80;
const COLUMN_MAX_WIDTH = 420;
const COLUMN_WIDTH_STORAGE_KEY = 'adminOperationCourseRatingColumnWidths';
const COLUMN_DEFAULT_WIDTHS = {
  ratedAt: 170,
  user: 220,
  lesson: 240,
  score: 90,
  comment: 320,
  mode: 110,
} as const;
const FILTER_ALL_OPTION = 'all';
const COMMENT_FILTER_COMMENTED_OPTION = 'commented';
const SORT_BY_LATEST_OPTION = 'latest_desc';
const SORT_BY_LOW_SCORE_OPTION = 'score_asc';

const EMPTY_RATINGS_RESPONSE: AdminOperationCourseRatingListResponse = {
  summary: {
    average_score: '',
    rating_count: 0,
    user_count: 0,
    latest_rated_at: '',
  },
  items: [],
  page: 1,
  page_size: PAGE_SIZE,
  total: 0,
  page_count: 0,
};

const createRatingFilters = (): RatingFilters => ({
  keyword: '',
  chapterKeyword: '',
  score: FILTER_ALL_OPTION,
  mode: FILTER_ALL_OPTION,
  commentFilter: FILTER_ALL_OPTION,
  sortBy: SORT_BY_LATEST_OPTION,
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

const resolvePrimaryAccount = ({
  mobile,
  email,
  contactMode,
  emptyValue,
}: {
  mobile?: string;
  email?: string;
  contactMode: ContactMode;
  emptyValue: string;
}) => {
  const preferred = contactMode === 'email' ? email : mobile;
  return formatValue(preferred, emptyValue);
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

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.operationsCourse.detail.ratings.back')
 * t('module.operationsCourse.detail.ratings.title')
 * t('module.operationsCourse.detail.ratings.openMetric')
 * t('module.operationsCourse.detail.ratings.emptyValue')
 * t('module.operationsCourse.detail.ratings.summary.averageScore')
 * t('module.operationsCourse.detail.ratings.summary.ratingCount')
 * t('module.operationsCourse.detail.ratings.summary.userCount')
 * t('module.operationsCourse.detail.ratings.summary.latestRatedAt')
 * t('module.operationsCourse.detail.ratings.summary.scopeHint')
 * t('module.operationsCourse.detail.ratings.filters.userKeyword')
 * t('module.operationsCourse.detail.ratings.filters.userKeywordPlaceholderPhone')
 * t('module.operationsCourse.detail.ratings.filters.userKeywordPlaceholderEmail')
 * t('module.operationsCourse.detail.ratings.filters.chapterKeyword')
 * t('module.operationsCourse.detail.ratings.filters.chapterKeywordPlaceholder')
 * t('module.operationsCourse.detail.ratings.filters.lessonKeyword')
 * t('module.operationsCourse.detail.ratings.filters.lessonKeywordPlaceholder')
 * t('module.operationsCourse.detail.ratings.filters.score')
 * t('module.operationsCourse.detail.ratings.filters.scoreAll')
 * t('module.operationsCourse.detail.ratings.filters.mode')
 * t('module.operationsCourse.detail.ratings.filters.modeAll')
 * t('module.operationsCourse.detail.ratings.filters.ratingTime')
 * t('module.operationsCourse.detail.ratings.filters.timePlaceholder')
 * t('module.operationsCourse.detail.ratings.filters.commentStatus')
 * t('module.operationsCourse.detail.ratings.filters.commentStatusAll')
 * t('module.operationsCourse.detail.ratings.filters.commentStatusCommented')
 * t('module.operationsCourse.detail.ratings.filters.sortBy')
 * t('module.operationsCourse.detail.ratings.filters.sortByLatest')
 * t('module.operationsCourse.detail.ratings.filters.sortByLowScore')
 * t('module.operationsCourse.detail.ratings.filters.resultCount')
 * t('module.operationsCourse.detail.ratings.filters.reset')
 * t('module.operationsCourse.detail.ratings.filters.search')
 * t('module.operationsCourse.detail.ratings.modes.read')
 * t('module.operationsCourse.detail.ratings.modes.listen')
 * t('module.operationsCourse.detail.ratings.scoreValue')
 * t('module.operationsCourse.detail.ratings.table.title')
 * t('module.operationsCourse.detail.ratings.table.ratedAt')
 * t('module.operationsCourse.detail.ratings.table.user')
 * t('module.operationsCourse.detail.ratings.table.chapter')
 * t('module.operationsCourse.detail.ratings.table.lesson')
 * t('module.operationsCourse.detail.ratings.table.score')
 * t('module.operationsCourse.detail.ratings.table.comment')
 * t('module.operationsCourse.detail.ratings.table.mode')
 * t('module.operationsCourse.detail.ratings.table.empty')
 * t('module.operationsCourse.detail.ratings.table.guestUser')
 */
export default function AdminOperationCourseRatingsPage() {
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');
  const router = useRouter();
  const params = useParams<{ shifu_bid?: string | string[] }>();
  const shifuBid = useMemo(() => {
    const rawValue = params?.shifu_bid;
    if (Array.isArray(rawValue)) {
      return rawValue[0]?.trim() || '';
    }
    return rawValue?.trim() || '';
  }, [params]);
  const { isReady } = useOperatorGuard();
  const unknownErrorMessage = t('common.core.unknownError');
  const emptyValue = tOperations('detail.ratings.emptyValue');
  const clearLabel = t('common.core.close');
  const defaultUserName = t('module.user.defaultUserName');
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);
  const contactMode = useMemo<ContactMode>(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );

  const [ratings, setRatings] =
    useState<AdminOperationCourseRatingListResponse>(EMPTY_RATINGS_RESPONSE);
  const [pageIndex, setPageIndex] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [filters, setFilters] = useState<RatingFilters>(createRatingFilters);
  const [filtersDraft, setFiltersDraft] =
    useState<RatingFilters>(createRatingFilters);
  const requestIdRef = useRef(0);

  const detailPageUrl = useMemo(
    () => buildAdminOperationsCourseDetailUrl(shifuBid),
    [shifuBid],
  );
  const currentPageUrl = useMemo(
    () => buildAdminOperationsCourseRatingsUrl(shifuBid),
    [shifuBid],
  );

  const { getColumnStyle, getResizeHandleProps } = useAdminResizableColumns({
    storageKey: COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: COLUMN_DEFAULT_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });

  const fetchRatings = useCallback(
    async (nextPage: number, nextFilters: RatingFilters) => {
      if (!shifuBid) {
        setRatings(EMPTY_RATINGS_RESPONSE);
        setError({ message: unknownErrorMessage });
        setLoading(false);
        return;
      }

      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setLoading(true);
      setError(null);
      try {
        const response = await api.getAdminOperationCourseRatings({
          shifu_bid: shifuBid,
          page: nextPage,
          page_size: PAGE_SIZE,
          keyword: nextFilters.keyword,
          chapter_keyword: nextFilters.chapterKeyword,
          score:
            nextFilters.score === FILTER_ALL_OPTION ? '' : nextFilters.score,
          mode: nextFilters.mode === FILTER_ALL_OPTION ? '' : nextFilters.mode,
          has_comment:
            nextFilters.commentFilter === COMMENT_FILTER_COMMENTED_OPTION
              ? 'true'
              : '',
          sort_by:
            nextFilters.sortBy === SORT_BY_LATEST_OPTION
              ? ''
              : nextFilters.sortBy,
          start_time: nextFilters.startTime,
          end_time: nextFilters.endTime,
        });
        if (requestId !== requestIdRef.current) {
          return;
        }
        setRatings(response || EMPTY_RATINGS_RESPONSE);
      } catch (err) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setRatings(EMPTY_RATINGS_RESPONSE);
        if (err instanceof ErrorWithCode) {
          setError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setError({ message: err.message });
        } else {
          setError({ message: unknownErrorMessage });
        }
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [shifuBid, unknownErrorMessage],
  );

  useEffect(() => {
    if (!isReady) {
      return;
    }
    fetchRatings(pageIndex, filters);
  }, [fetchRatings, filters, isReady, pageIndex]);

  const currentPage = ratings.page || 1;
  const pageCount = Math.max(ratings.page_count || 0, 1);
  const rows = useMemo(() => ratings.items || [], [ratings.items]);
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
    ? tOperations('detail.ratings.filters.chapterKeyword')
    : tOperations('detail.ratings.filters.lessonKeyword');
  const outlineFilterPlaceholder = hasChapterHierarchy
    ? tOperations('detail.ratings.filters.chapterKeywordPlaceholder')
    : tOperations('detail.ratings.filters.lessonKeywordPlaceholder');
  const outlineColumnLabel = hasChapterHierarchy
    ? tOperations('detail.ratings.table.chapter')
    : tOperations('detail.ratings.table.lesson');
  const summaryScopeHint = tOperations('detail.ratings.summary.scopeHint');
  const userKeywordInputId = 'rating-user-keyword-filter';
  const outlineKeywordInputId = 'rating-outline-keyword-filter';
  const ratingTimeFilterAriaLabel = tOperations(
    'detail.ratings.filters.ratingTime',
  );
  const userKeywordPlaceholder =
    contactMode === 'email'
      ? tOperations('detail.ratings.filters.userKeywordPlaceholderEmail')
      : tOperations('detail.ratings.filters.userKeywordPlaceholderPhone');

  const guestUserLabel = tOperations('detail.ratings.table.guestUser');

  const summaryCards = useMemo(
    () => [
      {
        key: 'averageScore',
        label: tOperations('detail.ratings.summary.averageScore'),
        value: ratings.summary.average_score || emptyValue,
        tone: 'number' as const,
      },
      {
        key: 'ratingCount',
        label: tOperations('detail.ratings.summary.ratingCount'),
        value: formatCount(ratings.summary.rating_count),
        tone: 'number' as const,
      },
      {
        key: 'userCount',
        label: tOperations('detail.ratings.summary.userCount'),
        value: formatCount(ratings.summary.user_count),
        tone: 'number' as const,
      },
      {
        key: 'latestRatedAt',
        label: tOperations('detail.ratings.summary.latestRatedAt'),
        value:
          formatAdminUtcDateTime(ratings.summary.latest_rated_at) || emptyValue,
        tone: 'timestamp' as const,
      },
    ],
    [emptyValue, ratings.summary, tOperations],
  );

  const resolveUserSecondary = useCallback(
    (item: AdminOperationCourseRatingItem) => {
      const nickname = item.nickname?.trim() || '';
      if (!nickname || nickname === defaultUserName) {
        return '';
      }
      return nickname;
    },
    [defaultUserName],
  );

  const resolveRatingModeLabel = useCallback(
    (mode: AdminOperationCourseRatingItem['mode']) => {
      if (mode === 'read') {
        return tOperations('detail.ratings.modes.read');
      }
      if (mode === 'listen') {
        return tOperations('detail.ratings.modes.listen');
      }
      return emptyValue;
    },
    [emptyValue, tOperations],
  );

  const handleSearch = useCallback(() => {
    const nextFilters = {
      keyword: filtersDraft.keyword.trim(),
      chapterKeyword: filtersDraft.chapterKeyword.trim(),
      score: filtersDraft.score,
      mode: filtersDraft.mode,
      commentFilter: filtersDraft.commentFilter,
      sortBy: filtersDraft.sortBy,
      startTime: filtersDraft.startTime,
      endTime: filtersDraft.endTime,
    };
    setFilters(nextFilters);
    setPageIndex(1);
  }, [filtersDraft]);

  const handleReset = useCallback(() => {
    const nextFilters = createRatingFilters();
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

  const primaryFilterItems = [
    {
      key: 'keyword',
      label: tOperations('detail.ratings.filters.userKeyword'),
      component: (
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
      ),
    },
    {
      key: 'chapterKeyword',
      label: outlineFilterLabel,
      component: (
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
      ),
    },
    {
      key: 'score',
      label: tOperations('detail.ratings.filters.score'),
      component: (
        <Select
          value={filtersDraft.score}
          onValueChange={value =>
            setFiltersDraft(previous => ({
              ...previous,
              score: value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={FILTER_ALL_OPTION}>
              {tOperations('detail.ratings.filters.scoreAll')}
            </SelectItem>
            {['5', '4', '3', '2', '1'].map(score => (
              <SelectItem
                key={score}
                value={score}
              >
                {tOperations('detail.ratings.scoreValue', {
                  count: Number(score),
                })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
  ];

  const topRowFilterItems = [
    ...primaryFilterItems,
    {
      key: 'mode',
      label: tOperations('detail.ratings.filters.mode'),
      component: (
        <Select
          value={filtersDraft.mode}
          onValueChange={value =>
            setFiltersDraft(previous => ({
              ...previous,
              mode: value as RatingModeFilter,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={FILTER_ALL_OPTION}>
              {tOperations('detail.ratings.filters.modeAll')}
            </SelectItem>
            <SelectItem value='read'>
              {tOperations('detail.ratings.modes.read')}
            </SelectItem>
            <SelectItem value='listen'>
              {tOperations('detail.ratings.modes.listen')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
  ];

  const secondRowFilterItems = [
    {
      key: 'ratingTime',
      label: tOperations('detail.ratings.filters.ratingTime'),
      component: (
        <AdminDateRangeFilter
          startValue={filtersDraft.startTime}
          endValue={filtersDraft.endTime}
          triggerAriaLabel={ratingTimeFilterAriaLabel}
          placeholder={tOperations('detail.ratings.filters.timePlaceholder')}
          resetLabel={tOperations('detail.ratings.filters.reset')}
          clearLabel={clearLabel}
          onChange={({ start, end }) =>
            setFiltersDraft(previous => ({
              ...previous,
              startTime: start,
              endTime: end,
            }))
          }
        />
      ),
    },
    {
      key: 'commentFilter',
      label: tOperations('detail.ratings.filters.commentStatus'),
      component: (
        <Select
          value={filtersDraft.commentFilter}
          onValueChange={value =>
            setFiltersDraft(previous => ({
              ...previous,
              commentFilter: value as RatingCommentFilter,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={FILTER_ALL_OPTION}>
              {tOperations('detail.ratings.filters.commentStatusAll')}
            </SelectItem>
            <SelectItem value={COMMENT_FILTER_COMMENTED_OPTION}>
              {tOperations('detail.ratings.filters.commentStatusCommented')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'sortBy',
      label: tOperations('detail.ratings.filters.sortBy'),
      component: (
        <Select
          value={filtersDraft.sortBy}
          onValueChange={value =>
            setFiltersDraft(previous => ({
              ...previous,
              sortBy: value as RatingSortBy,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={SORT_BY_LATEST_OPTION}>
              {tOperations('detail.ratings.filters.sortByLatest')}
            </SelectItem>
            <SelectItem value={SORT_BY_LOW_SCORE_OPTION}>
              {tOperations('detail.ratings.filters.sortByLowScore')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
  ];

  const renderResizeHandle = useCallback(
    (columnKey: keyof typeof COLUMN_DEFAULT_WIDTHS) => (
      <span
        className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
        {...getResizeHandleProps(columnKey)}
      />
    ),
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
              {tOperations('detail.ratings.title')}
            </h1>
            <p className='text-sm text-muted-foreground'>{summaryScopeHint}</p>
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
            {tOperations('detail.ratings.back')}
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
                    {tOperations('detail.ratings.table.title')}
                  </CardTitle>
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
                  <div className='space-y-4'>
                    <div className='grid gap-4 xl:grid-cols-4'>
                      {topRowFilterItems.map(item => (
                        <div
                          key={item.key}
                          className='flex items-center'
                        >
                          <span className='mr-2 w-20 shrink-0 whitespace-nowrap text-right text-sm font-medium text-foreground after:ml-0.5 after:content-[":"]'>
                            {item.label}
                          </span>
                          <div className='min-w-0 flex-1'>{item.component}</div>
                        </div>
                      ))}
                    </div>

                    {expanded ? (
                      <div className='grid gap-4 xl:grid-cols-4'>
                        {secondRowFilterItems.map(item => (
                          <div
                            key={item.key}
                            className='flex items-center'
                          >
                            <span className='mr-2 w-20 shrink-0 whitespace-nowrap text-right text-sm font-medium text-foreground after:ml-0.5 after:content-[":"]'>
                              {item.label}
                            </span>
                            <div className='min-w-0 flex-1'>
                              {item.component}
                            </div>
                          </div>
                        ))}
                        <div className='hidden xl:block' />
                      </div>
                    ) : null}

                    <div className='flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between'>
                      <div className='flex min-h-9 items-end text-sm text-muted-foreground'>
                        {tOperations('detail.ratings.filters.resultCount', {
                          count: ratings.total,
                        })}
                      </div>
                      <div className='flex items-center justify-start gap-2 xl:justify-end'>
                        <Button
                          type='button'
                          size='sm'
                          variant='outline'
                          className='h-9 px-4'
                          onClick={handleReset}
                          disabled={loading}
                        >
                          {tOperations('detail.ratings.filters.reset')}
                        </Button>
                        <Button
                          type='submit'
                          size='sm'
                          className='h-9 px-4'
                          disabled={loading}
                        >
                          {tOperations('detail.ratings.filters.search')}
                        </Button>
                        <Button
                          type='button'
                          size='sm'
                          variant='ghost'
                          className='px-2 text-primary'
                          onClick={() => setExpanded(previous => !previous)}
                        >
                          {expanded
                            ? t('common.core.collapse')
                            : t('common.core.expand')}
                          {expanded ? (
                            <ChevronUp className='ml-1 h-4 w-4' />
                          ) : (
                            <ChevronDown className='ml-1 h-4 w-4' />
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                </form>

                {error ? (
                  <ErrorDisplay
                    errorCode={error.code || 0}
                    errorMessage={error.message}
                    onRetry={() => fetchRatings(pageIndex, filters)}
                  />
                ) : (
                  <AdminTableShell
                    loading={loading}
                    isEmpty={rows.length === 0}
                    emptyContent={tOperations('detail.ratings.table.empty')}
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
                              style={getColumnStyle('ratedAt')}
                            >
                              {tOperations('detail.ratings.table.ratedAt')}
                              {renderResizeHandle('ratedAt')}
                            </TableHead>
                            <TableHead
                              className={cn(
                                ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('user')}
                            >
                              {tOperations('detail.ratings.table.user')}
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
                              style={getColumnStyle('score')}
                            >
                              {tOperations('detail.ratings.table.score')}
                              {renderResizeHandle('score')}
                            </TableHead>
                            <TableHead
                              className={cn(
                                ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('comment')}
                            >
                              {tOperations('detail.ratings.table.comment')}
                              {renderResizeHandle('comment')}
                            </TableHead>
                            <TableHead
                              className={cn(
                                ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                                'h-10 whitespace-nowrap bg-muted/80 text-xs',
                              )}
                              style={getColumnStyle('mode')}
                            >
                              {tOperations('detail.ratings.table.mode')}
                              {renderResizeHandle('mode')}
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
                                  contactMode,
                                  emptyValue,
                                });
                                const secondaryAccount =
                                  resolveUserSecondary(item);
                                const isGuestAccount =
                                  !item.mobile?.trim() && !item.email?.trim();
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
                                return (
                                  <TableRow key={item.lesson_feedback_bid}>
                                    <TableCell
                                      className='whitespace-nowrap border-r border-border py-3 text-center align-top text-sm text-foreground/80 last:border-r-0'
                                      style={getColumnStyle('ratedAt')}
                                    >
                                      <AdminTooltipText
                                        text={formatAdminUtcDateTime(
                                          item.rated_at,
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
                                        {isGuestAccount ? (
                                          <div className='flex justify-center text-sm text-muted-foreground'>
                                            <span>{guestUserLabel}</span>
                                          </div>
                                        ) : (
                                          <div className='font-medium text-foreground'>
                                            <AdminTooltipText
                                              text={primaryAccount}
                                              emptyValue={emptyValue}
                                              className='mx-auto block max-w-full text-sm text-foreground'
                                            />
                                          </div>
                                        )}
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
                                      className='whitespace-nowrap border-r border-border py-3 text-center align-top text-sm font-medium text-foreground last:border-r-0'
                                      style={getColumnStyle('score')}
                                    >
                                      {tOperations(
                                        'detail.ratings.scoreValue',
                                        {
                                          count: item.score,
                                        },
                                      )}
                                    </TableCell>
                                    <TableCell
                                      className='border-r border-border py-3 align-top last:border-r-0'
                                      style={getColumnStyle('comment')}
                                    >
                                      <AdminTooltipText
                                        text={item.comment}
                                        emptyValue={emptyValue}
                                        className='block max-w-full text-sm text-foreground'
                                      />
                                    </TableCell>
                                    <TableCell
                                      className='whitespace-nowrap py-3 text-center align-top text-sm text-foreground last:border-r-0'
                                      style={getColumnStyle('mode')}
                                    >
                                      {resolveRatingModeLabel(item.mode)}
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
                        prevLabel={t('module.order.paginationPrev')}
                        nextLabel={t('module.order.paginationNext')}
                        prevAriaLabel={t(
                          'module.order.paginationPrevAriaLabel',
                        )}
                        nextAriaLabel={t(
                          'module.order.paginationNextAriaLabel',
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
    </div>
  );
}
