'use client';

import { X } from 'lucide-react';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
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
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { cn } from '@/lib/utils';
import { useUserStore } from '@/store';
import type {
  DashboardCourseRatingItem,
  DashboardCourseRatingListResponse,
} from '@/types/dashboard';
import {
  DASHBOARD_FILTER_CONTENT_CLASS,
  DASHBOARD_FILTER_LABEL_CLASS,
} from '../../dashboardFilterUiShared';
import { buildAdminDashboardCourseDetailUrl } from '../../admin-dashboard-routes';

type ErrorState = { message: string; code?: number };
type ContactMode = 'phone' | 'email';
type RatingCommentFilter = 'all' | 'commented';

type RatingFilters = {
  keyword: string;
  chapterKeyword: string;
  score: string;
  commentFilter: RatingCommentFilter;
  startTime: string;
  endTime: string;
};

const PAGE_SIZE = 20;
const FILTER_ALL_OPTION = 'all';
const COMMENT_FILTER_COMMENTED_OPTION = 'commented';
const RATINGS_SCORE_LABEL_ID = 'ratings-score-label';
const RATINGS_SCORE_TRIGGER_ID = 'ratings-score-trigger';
const RATINGS_COMMENT_STATUS_LABEL_ID = 'ratings-comment-status-label';
const RATINGS_COMMENT_STATUS_TRIGGER_ID = 'ratings-comment-status-trigger';
const RATINGS_FILTER_GRID_CLASS =
  'gap-x-6 md:grid-cols-2 xl:grid-cols-[minmax(0,280px)_minmax(0,280px)_minmax(0,152px)_minmax(0,172px)_minmax(0,286px)]';
const RATINGS_FILTER_LABEL_SM_CLASS = 'w-[60px]';
const RATINGS_FILTER_LABEL_MD_CLASS = 'w-[88px]';

const EMPTY_RATINGS_RESPONSE: DashboardCourseRatingListResponse = {
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
  commentFilter: FILTER_ALL_OPTION,
  startTime: '',
  endTime: '',
});

const formatCount = (
  value: number,
  emptyValue: string,
  locale: string,
): string => {
  if (!Number.isFinite(value)) {
    return emptyValue;
  }
  return value.toLocaleString(locale);
};

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

const resolvePrimaryUserDisplay = ({
  nickname,
  mobile,
  email,
  userBid,
  contactMode,
  guestUserLabel,
}: {
  nickname?: string;
  mobile?: string;
  email?: string;
  userBid?: string;
  contactMode: ContactMode;
  guestUserLabel: string;
}) => {
  const normalizedNickname = nickname?.trim() || '';
  if (normalizedNickname) {
    return normalizedNickname;
  }
  const preferredContact = contactMode === 'email' ? email : mobile;
  const alternateContact = contactMode === 'email' ? mobile : email;
  return (
    preferredContact?.trim() ||
    alternateContact?.trim() ||
    userBid?.trim() ||
    guestUserLabel
  );
};

const resolveSecondaryUserDisplay = ({
  nickname,
  mobile,
  email,
  userBid,
  contactMode,
}: {
  nickname?: string;
  mobile?: string;
  email?: string;
  userBid?: string;
  contactMode: ContactMode;
}) => {
  const preferredContact = contactMode === 'email' ? email : mobile;
  const alternateContact = contactMode === 'email' ? mobile : email;
  const contact = preferredContact?.trim() || alternateContact?.trim() || '';
  if (nickname?.trim()) {
    return contact || userBid?.trim() || '';
  }
  if (contact && userBid?.trim() && contact !== userBid.trim()) {
    return userBid.trim();
  }
  return '';
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

export default function AdminDashboardCourseRatingsPage() {
  const { t, i18n } = useTranslation();
  const params = useParams<{ shifu_bid?: string }>();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const detailPageUrl = useMemo(
    () => buildAdminDashboardCourseDetailUrl(shifuBid),
    [shifuBid],
  );
  const emptyValue = t('module.dashboard.detail.ratings.emptyValue');
  const clearLabel = t('common.core.close');
  const unknownErrorMessage = t('common.core.unknownError');
  const guestUserLabel = t('module.dashboard.detail.ratings.table.guestUser');
  const contactMode = useMemo<ContactMode>(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const userKeywordPlaceholder = useMemo(
    () =>
      contactMode === 'email'
        ? t(
            'module.dashboard.detail.ratings.filters.userKeywordPlaceholderEmail',
          )
        : t(
            'module.dashboard.detail.ratings.filters.userKeywordPlaceholderPhone',
          ),
    [contactMode, t],
  );

  const [ratings, setRatings] = useState<DashboardCourseRatingListResponse>(
    EMPTY_RATINGS_RESPONSE,
  );
  const [pageIndex, setPageIndex] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [filters, setFilters] = useState<RatingFilters>(createRatingFilters);
  const [filtersDraft, setFiltersDraft] =
    useState<RatingFilters>(createRatingFilters);
  const requestIdRef = useRef(0);

  const fetchRatings = useCallback(
    async (nextPage: number, nextFilters: RatingFilters) => {
      if (!shifuBid.trim()) {
        setRatings(EMPTY_RATINGS_RESPONSE);
        setError({ message: unknownErrorMessage });
        return;
      }

      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getDashboardCourseRatings({
          shifu_bid: shifuBid,
          page_index: nextPage,
          page_size: PAGE_SIZE,
          keyword: nextFilters.keyword,
          chapter_keyword: nextFilters.chapterKeyword,
          score:
            nextFilters.score === FILTER_ALL_OPTION ? '' : nextFilters.score,
          has_comment:
            nextFilters.commentFilter === COMMENT_FILTER_COMMENTED_OPTION
              ? 'true'
              : '',
          start_time: nextFilters.startTime,
          end_time: nextFilters.endTime,
        })) as DashboardCourseRatingListResponse;
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
    fetchRatings(pageIndex, filters);
  }, [fetchRatings, filters, isGuest, isInitialized, pageIndex]);

  const handleSearch = useCallback(() => {
    setPageIndex(1);
    setFilters({
      keyword: filtersDraft.keyword.trim(),
      chapterKeyword: filtersDraft.chapterKeyword.trim(),
      score: filtersDraft.score,
      commentFilter: filtersDraft.commentFilter,
      startTime: filtersDraft.startTime,
      endTime: filtersDraft.endTime,
    });
  }, [filtersDraft]);

  const handleReset = useCallback(() => {
    const nextFilters = createRatingFilters();
    setFiltersDraft(nextFilters);
    setFilters(nextFilters);
    setPageIndex(1);
  }, []);

  const rows = useMemo(() => ratings.items || [], [ratings.items]);
  const summaryCards = useMemo(
    () => [
      {
        label: t('module.dashboard.detail.ratings.summary.averageScore'),
        value: ratings.summary.average_score || emptyValue,
        tone: 'default' as const,
      },
      {
        label: t('module.dashboard.detail.ratings.summary.ratingCount'),
        value: formatCount(
          ratings.summary.rating_count,
          emptyValue,
          i18n.language,
        ),
        tone: 'default' as const,
      },
      {
        label: t('module.dashboard.detail.ratings.summary.userCount'),
        value: formatCount(
          ratings.summary.user_count,
          emptyValue,
          i18n.language,
        ),
        tone: 'default' as const,
      },
      {
        label: t('module.dashboard.detail.ratings.summary.latestRatedAt'),
        value:
          formatAdminUtcDateTime(ratings.summary.latest_rated_at) || emptyValue,
        tone: 'timestamp' as const,
      },
    ],
    [emptyValue, i18n.language, ratings.summary, t],
  );
  const scoreOptions = useMemo(
    () => [
      {
        value: FILTER_ALL_OPTION,
        label: t('module.dashboard.detail.ratings.filters.scoreAll'),
      },
      ...[5, 4, 3, 2, 1].map(scoreValue => ({
        value: String(scoreValue),
        label: t('module.dashboard.detail.ratings.scoreValue', {
          score: scoreValue,
        }),
      })),
    ],
    [t],
  );
  const commentStatusOptions = useMemo(
    () => [
      {
        value: FILTER_ALL_OPTION,
        label: t('module.dashboard.detail.ratings.filters.commentStatusAll'),
      },
      {
        value: COMMENT_FILTER_COMMENTED_OPTION,
        label: t(
          'module.dashboard.detail.ratings.filters.commentStatusCommented',
        ),
      },
    ],
    [t],
  );
  const filterItems: AdminFilterItem[] = [
    createTextFilterItem({
      key: 'keyword',
      label: t('module.dashboard.detail.ratings.filters.userKeyword'),
      value: filtersDraft.keyword,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          keyword: value,
        })),
      onSubmit: handleSearch,
      placeholder: userKeywordPlaceholder,
      clearLabel,
      labelClassName: RATINGS_FILTER_LABEL_SM_CLASS,
      contentClassName: 'min-w-0 flex-[1.15]',
      inputClassName: 'min-w-0',
    }),
    createTextFilterItem({
      key: 'chapter_keyword',
      label: t('module.dashboard.detail.ratings.filters.chapterKeyword'),
      value: filtersDraft.chapterKeyword,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          chapterKeyword: value,
        })),
      onSubmit: handleSearch,
      placeholder: t(
        'module.dashboard.detail.ratings.filters.chapterKeywordPlaceholder',
      ),
      clearLabel,
      labelClassName: RATINGS_FILTER_LABEL_SM_CLASS,
      contentClassName: 'min-w-0 flex-[1.15]',
      inputClassName: 'min-w-0',
    }),
    createSelectFilterItem({
      key: 'score',
      label: t('module.dashboard.detail.ratings.filters.score'),
      labelId: RATINGS_SCORE_LABEL_ID,
      value: filtersDraft.score,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          score: value,
        })),
      triggerId: RATINGS_SCORE_TRIGGER_ID,
      triggerAriaLabelledBy: RATINGS_SCORE_LABEL_ID,
      labelClassName: RATINGS_FILTER_LABEL_SM_CLASS,
      placeholder: t('module.dashboard.detail.ratings.filters.scoreAll'),
      options: scoreOptions,
      triggerClassName: 'min-w-[108px]',
    }),
    createSelectFilterItem({
      key: 'comment_filter',
      label: t('module.dashboard.detail.ratings.filters.commentStatus'),
      labelId: RATINGS_COMMENT_STATUS_LABEL_ID,
      value: filtersDraft.commentFilter,
      onChange: value =>
        setFiltersDraft(previous => ({
          ...previous,
          commentFilter: value as RatingCommentFilter,
        })),
      triggerId: RATINGS_COMMENT_STATUS_TRIGGER_ID,
      triggerAriaLabelledBy: RATINGS_COMMENT_STATUS_LABEL_ID,
      labelClassName: RATINGS_FILTER_LABEL_MD_CLASS,
      placeholder: t(
        'module.dashboard.detail.ratings.filters.commentStatusAll',
      ),
      options: commentStatusOptions,
      triggerClassName: 'min-w-[120px]',
    }),
    createDateRangeFilterItem({
      key: 'date_range',
      label: t('module.dashboard.detail.ratings.filters.ratingTime'),
      startValue: filtersDraft.startTime,
      endValue: filtersDraft.endTime,
      onChange: ({ start, end }) =>
        setFiltersDraft(previous => ({
          ...previous,
          startTime: start,
          endTime: end,
        })),
      labelClassName: RATINGS_FILTER_LABEL_MD_CLASS,
      placeholder: t('module.dashboard.detail.ratings.filters.timePlaceholder'),
      resetLabel: t('module.dashboard.detail.ratings.filters.reset'),
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
            { label: t('module.dashboard.detail.ratings.title') },
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
              <CardTitle className='text-base font-semibold tracking-normal'>
                {t('module.dashboard.detail.ratings.table.title')}
              </CardTitle>
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
                    'module.dashboard.detail.ratings.filters.reset',
                  )}
                  searchLabel={t(
                    'module.dashboard.detail.ratings.filters.search',
                  )}
                  expandLabel={t('common.core.expand')}
                  collapseLabel={t('common.core.collapse')}
                  collapsedCount={5}
                  showToggle={false}
                  labelClassName={DASHBOARD_FILTER_LABEL_CLASS}
                  contentClassName={DASHBOARD_FILTER_CONTENT_CLASS}
                  collapsedGridClassName={RATINGS_FILTER_GRID_CLASS}
                  expandedGridClassName={RATINGS_FILTER_GRID_CLASS}
                />
                <div className='mt-3 flex flex-col gap-3 pl-1 sm:flex-row sm:items-center sm:justify-between'>
                  <div className='text-sm text-muted-foreground'>
                    {t('module.dashboard.detail.ratings.filters.resultCount', {
                      count: ratings.total,
                    })}
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
                      {t('module.dashboard.detail.ratings.filters.reset')}
                    </Button>
                    <Button
                      type='button'
                      size='sm'
                      className='h-9 px-4'
                      onClick={handleSearch}
                      disabled={loading}
                    >
                      {t('module.dashboard.detail.ratings.filters.search')}
                    </Button>
                  </div>
                </div>
              </div>

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
                  emptyContent={t(
                    'module.dashboard.detail.ratings.table.empty',
                  )}
                  emptyColSpan={5}
                  withTooltipProvider
                  tableWrapperClassName='overflow-auto'
                  loadingClassName='min-h-[240px]'
                  footer={
                    ratings.page_count > 1 ? (
                      <AdminPagination
                        pageIndex={ratings.page || 1}
                        pageCount={ratings.page_count}
                        onPageChange={nextPage => setPageIndex(nextPage)}
                        prevLabel={t('module.dashboard.pagination.prev')}
                        nextLabel={t('module.dashboard.pagination.next')}
                        prevAriaLabel={t('module.dashboard.pagination.prev')}
                        nextAriaLabel={t('module.dashboard.pagination.next')}
                        className='mx-0 w-auto justify-end'
                      />
                    ) : null
                  }
                  table={emptyRow => (
                    <Table className='table-auto'>
                      <TableHeader>
                        <TableRow>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-left text-xs'>
                            {t('module.dashboard.detail.ratings.table.ratedAt')}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-left text-xs'>
                            {t('module.dashboard.detail.ratings.table.user')}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-left text-xs'>
                            {t('module.dashboard.detail.ratings.table.lesson')}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-left text-xs'>
                            {t('module.dashboard.detail.ratings.table.score')}
                          </TableHead>
                          <TableHead className='h-10 whitespace-nowrap bg-muted/80 text-left text-xs'>
                            {t('module.dashboard.detail.ratings.table.comment')}
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {rows.length === 0
                          ? emptyRow
                          : rows.map((item: DashboardCourseRatingItem) => {
                              const primaryUser = resolvePrimaryUserDisplay({
                                nickname: item.nickname,
                                mobile: item.mobile,
                                email: item.email,
                                userBid: item.user_bid,
                                contactMode,
                                guestUserLabel,
                              });
                              const secondaryUser = resolveSecondaryUserDisplay(
                                {
                                  nickname: item.nickname,
                                  mobile: item.mobile,
                                  email: item.email,
                                  userBid: item.user_bid,
                                  contactMode,
                                },
                              );
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
                              const scoreLabel = t(
                                'module.dashboard.detail.ratings.scoreValue',
                                { score: item.score },
                              );
                              return (
                                <TableRow key={item.lesson_feedback_bid}>
                                  <TableCell className='whitespace-nowrap py-3 align-middle text-sm text-foreground/80'>
                                    <AdminTooltipText
                                      text={formatAdminUtcDateTime(
                                        item.rated_at,
                                      )}
                                      emptyValue={emptyValue}
                                      className='block max-w-[180px]'
                                    />
                                  </TableCell>
                                  <TableCell className='py-3 align-middle'>
                                    <div className='flex flex-col gap-0.5 leading-tight'>
                                      <div className='font-medium text-foreground'>
                                        <AdminTooltipText
                                          text={primaryUser}
                                          emptyValue={guestUserLabel}
                                          className='block max-w-[180px] text-sm text-foreground'
                                        />
                                      </div>
                                      {secondaryUser ? (
                                        <div className='text-xs text-muted-foreground'>
                                          <AdminTooltipText
                                            text={secondaryUser}
                                            emptyValue=''
                                            className='block max-w-[180px] text-xs text-muted-foreground'
                                          />
                                        </div>
                                      ) : null}
                                    </div>
                                  </TableCell>
                                  <TableCell className='py-3 align-middle'>
                                    <div className='flex flex-col gap-0.5 leading-tight'>
                                      <div className='font-medium text-foreground'>
                                        <AdminTooltipText
                                          text={primaryLessonDisplay}
                                          emptyValue={emptyValue}
                                          className='block max-w-[220px] text-sm text-foreground'
                                        />
                                      </div>
                                      {secondaryChapterDisplay ? (
                                        <div className='text-xs text-muted-foreground'>
                                          <AdminTooltipText
                                            text={secondaryChapterDisplay}
                                            emptyValue=''
                                            className='block max-w-[220px] text-xs text-muted-foreground'
                                          />
                                        </div>
                                      ) : null}
                                    </div>
                                  </TableCell>
                                  <TableCell className='whitespace-nowrap py-3 align-middle text-sm font-medium text-foreground'>
                                    {scoreLabel}
                                  </TableCell>
                                  <TableCell className='py-3 align-middle text-sm text-foreground/80'>
                                    <AdminTooltipText
                                      text={item.comment}
                                      emptyValue={emptyValue}
                                      className='block max-w-[360px] whitespace-normal break-words'
                                    />
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                      </TableBody>
                    </Table>
                  )}
                />
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
