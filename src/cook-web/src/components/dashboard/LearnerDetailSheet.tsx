'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '@/api';
import { useTranslation } from 'react-i18next';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import Loading from '@/components/loading';
import ErrorDisplay from '@/components/ErrorDisplay';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
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
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';
import { ErrorWithCode } from '@/lib/request';
import type {
  DashboardFollowUpItem,
  DashboardLearnerDetail,
  DashboardPage,
} from '@/types/dashboard';

type LearnerDetailSheetProps = {
  open: boolean;
  shifuBid: string;
  userBid?: string;
  startDate?: string;
  endDate?: string;
  onOpenChange?: (open: boolean) => void;
};

type ErrorState = { message: string; code?: number };

const FOLLOWUPS_OUTLINE_ALL_VALUE = '__all__';

const resolveLearnStatusLabel = (
  status: number,
  t: (key: string) => string,
) => {
  if (status === 602) {
    return t('server.order.learnStatusInProgress');
  }
  if (status === 603) {
    return t('server.order.learnStatusCompleted');
  }
  if (status === 604) {
    return t('server.order.learnStatusRefund');
  }
  if (status === 605) {
    return t('server.order.learnStatusLocked');
  }
  if (status === 606) {
    return t('server.order.learnStatusUnavailable');
  }
  if (status === 607) {
    return t('server.order.learnStatusBranch');
  }
  if (status === 608) {
    return t('server.order.learnStatusReset');
  }
  return t('server.order.learnStatusNotStarted');
};

const resolveLearnStatusVariant = (status: number) => {
  if (status === 603) {
    return 'default';
  }
  if (status === 602) {
    return 'secondary';
  }
  return 'outline';
};

export default function LearnerDetailSheet({
  open,
  shifuBid,
  userBid,
  startDate,
  endDate,
  onOpenChange,
}: LearnerDetailSheetProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<
    'progress' | 'followups' | 'profile'
  >('progress');

  const [detail, setDetail] = useState<DashboardLearnerDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ErrorState | null>(null);

  const [followups, setFollowups] = useState<DashboardFollowUpItem[]>([]);
  const [followupsLoading, setFollowupsLoading] = useState(false);
  const [followupsError, setFollowupsError] = useState<ErrorState | null>(null);
  const [followupsPageIndex, setFollowupsPageIndex] = useState(1);
  const [followupsPageCount, setFollowupsPageCount] = useState(1);
  const [followupsTotal, setFollowupsTotal] = useState(0);
  const [followupsOutlineBid, setFollowupsOutlineBid] = useState(
    FOLLOWUPS_OUTLINE_ALL_VALUE,
  );

  const outlineOptions = useMemo(() => {
    const items = detail?.outlines || [];
    return items
      .filter(item => item && item.outline_item_bid)
      .map(item => ({
        bid: item.outline_item_bid,
        title: item.title || item.outline_item_bid,
      }));
  }, [detail?.outlines]);

  const fetchDetail = useCallback(async () => {
    if (!open || !shifuBid || !userBid) {
      setDetail(null);
      setDetailLoading(false);
      setDetailError(null);
      return;
    }

    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const result = (await api.getDashboardLearnerDetail({
        shifu_bid: shifuBid,
        user_bid: userBid,
      })) as DashboardLearnerDetail;
      setDetail(result);
    } catch (err) {
      setDetail(null);
      if (err instanceof ErrorWithCode) {
        setDetailError({ message: err.message, code: err.code });
      } else if (err instanceof Error) {
        setDetailError({ message: err.message });
      } else {
        setDetailError({ message: t('common.core.unknownError') });
      }
    } finally {
      setDetailLoading(false);
    }
  }, [open, shifuBid, t, userBid]);

  const fetchFollowups = useCallback(
    async (targetPage: number) => {
      if (!open || !shifuBid || !userBid) {
        setFollowups([]);
        setFollowupsLoading(false);
        setFollowupsError(null);
        setFollowupsPageIndex(1);
        setFollowupsPageCount(1);
        setFollowupsTotal(0);
        return;
      }

      setFollowupsLoading(true);
      setFollowupsError(null);
      try {
        const response = (await api.getDashboardLearnerFollowups({
          shifu_bid: shifuBid,
          user_bid: userBid,
          outline_item_bid:
            followupsOutlineBid === FOLLOWUPS_OUTLINE_ALL_VALUE
              ? undefined
              : followupsOutlineBid,
          start_time: startDate || undefined,
          end_time: endDate || undefined,
          page_index: targetPage,
          page_size: 20,
        })) as DashboardPage<DashboardFollowUpItem>;

        setFollowups(response.items || []);
        setFollowupsPageIndex(response.page || targetPage);
        setFollowupsPageCount(response.page_count || 1);
        setFollowupsTotal(response.total || 0);
      } catch (err) {
        setFollowups([]);
        setFollowupsPageIndex(targetPage);
        setFollowupsPageCount(1);
        setFollowupsTotal(0);
        if (err instanceof ErrorWithCode) {
          setFollowupsError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setFollowupsError({ message: err.message });
        } else {
          setFollowupsError({ message: t('common.core.unknownError') });
        }
      } finally {
        setFollowupsLoading(false);
      }
    },
    [endDate, followupsOutlineBid, open, shifuBid, startDate, t, userBid],
  );

  useEffect(() => {
    if (!open) {
      setActiveTab('progress');
      setDetail(null);
      setDetailLoading(false);
      setDetailError(null);
      setFollowups([]);
      setFollowupsLoading(false);
      setFollowupsError(null);
      setFollowupsPageIndex(1);
      setFollowupsPageCount(1);
      setFollowupsTotal(0);
      setFollowupsOutlineBid(FOLLOWUPS_OUTLINE_ALL_VALUE);
      return;
    }
    fetchDetail();
  }, [fetchDetail, open]);

  useEffect(() => {
    if (!open || activeTab !== 'followups') {
      return;
    }
    fetchFollowups(1);
  }, [activeTab, fetchFollowups, open]);

  const handleFollowupsPageChange = (nextPage: number) => {
    if (
      nextPage < 1 ||
      nextPage > followupsPageCount ||
      nextPage === followupsPageIndex
    ) {
      return;
    }
    fetchFollowups(nextPage);
  };

  const followupsPages = useMemo(() => {
    const startPage =
      followupsPageCount <= 5
        ? 1
        : Math.max(1, Math.min(followupsPageIndex - 2, followupsPageCount - 4));
    const endPage =
      followupsPageCount <= 5
        ? followupsPageCount
        : Math.min(followupsPageCount, startPage + 4);

    const pages: number[] = [];
    for (let page = startPage; page <= endPage; page += 1) {
      pages.push(page);
    }
    return pages;
  }, [followupsPageCount, followupsPageIndex]);

  const titleText = useMemo(() => {
    if (!detail) {
      return t('module.dashboard.detail.title');
    }
    const primary = detail.mobile || detail.user_bid;
    const secondary = detail.nickname ? ` (${detail.nickname})` : '';
    return `${primary}${secondary}`;
  }, [detail, t]);

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[420px] md:w-[620px] lg:w-[760px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
          <SheetTitle className='flex flex-col gap-1'>
            <span className='text-xs font-medium text-muted-foreground'>
              {t('module.dashboard.detail.subtitle')}
            </span>
            <span className='text-base font-semibold text-foreground'>
              {titleText}
            </span>
          </SheetTitle>
        </SheetHeader>

        <div className='flex-1 overflow-y-auto px-6 py-5'>
          {detailLoading ? (
            <div className='flex h-40 items-center justify-center'>
              <Loading />
            </div>
          ) : detailError ? (
            <ErrorDisplay
              errorCode={detailError.code || 500}
              errorMessage={detailError.message}
              onRetry={fetchDetail}
            />
          ) : (
            <Tabs
              value={activeTab}
              onValueChange={value =>
                setActiveTab(value as 'progress' | 'followups' | 'profile')
              }
            >
              <TabsList className='w-full justify-start'>
                <TabsTrigger value='progress'>
                  {t('module.dashboard.detail.tabs.progress')}
                </TabsTrigger>
                <TabsTrigger value='followups'>
                  {t('module.dashboard.detail.tabs.followUps')}
                </TabsTrigger>
                <TabsTrigger value='profile'>
                  {t('module.dashboard.detail.tabs.personalization')}
                </TabsTrigger>
              </TabsList>

              <TabsContent value='progress'>
                <div className='overflow-auto rounded-lg border border-border bg-white'>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>
                          {t('module.dashboard.detail.progress.outline')}
                        </TableHead>
                        <TableHead>
                          {t('module.dashboard.detail.progress.status')}
                        </TableHead>
                        <TableHead>
                          {t('module.dashboard.detail.progress.updatedAt')}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(detail?.outlines || []).length === 0 && (
                        <TableEmpty colSpan={3}>
                          {t('module.dashboard.detail.progress.empty')}
                        </TableEmpty>
                      )}
                      {(detail?.outlines || []).map(item => (
                        <TableRow key={item.outline_item_bid}>
                          <TableCell className='min-w-[240px]'>
                            <div className='text-sm text-foreground'>
                              {item.title || item.outline_item_bid}
                            </div>
                            <div className='text-xs text-muted-foreground'>
                              {item.outline_item_bid}
                            </div>
                          </TableCell>
                          <TableCell className='whitespace-nowrap'>
                            <Badge
                              variant={resolveLearnStatusVariant(item.status)}
                            >
                              {resolveLearnStatusLabel(item.status, t)}
                            </Badge>
                          </TableCell>
                          <TableCell className='whitespace-nowrap'>
                            {item.updated_at || '-'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>

              <TabsContent value='followups'>
                <div className='flex flex-col gap-3'>
                  <div className='flex flex-col gap-2 md:flex-row md:items-center md:justify-between'>
                    <div className='flex items-baseline gap-2'>
                      <div className='text-sm font-medium text-foreground'>
                        {t('module.dashboard.detail.followUps.title')}
                      </div>
                      <div className='text-xs text-muted-foreground'>
                        {t('module.dashboard.detail.followUps.totalCount', {
                          count: followupsTotal,
                        })}
                      </div>
                    </div>
                    <div className='flex items-center gap-2'>
                      <Select
                        value={followupsOutlineBid}
                        onValueChange={value => {
                          setFollowupsOutlineBid(value);
                          setFollowupsPageIndex(1);
                        }}
                      >
                        <SelectTrigger className='h-9 w-[260px] max-w-[80vw]'>
                          <SelectValue
                            placeholder={t(
                              'module.dashboard.detail.followUps.outlinePlaceholder',
                            )}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={FOLLOWUPS_OUTLINE_ALL_VALUE}>
                            {t('common.core.all')}
                          </SelectItem>
                          {outlineOptions.map(option => (
                            <SelectItem
                              key={option.bid}
                              value={option.bid}
                            >
                              {option.title}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        size='sm'
                        variant='outline'
                        type='button'
                        onClick={() => fetchFollowups(1)}
                      >
                        {t('common.core.retry')}
                      </Button>
                    </div>
                  </div>

                  {followupsError &&
                  !followupsLoading &&
                  followups.length === 0 ? (
                    <ErrorDisplay
                      errorCode={followupsError.code || 500}
                      errorMessage={followupsError.message}
                      onRetry={() => fetchFollowups(1)}
                    />
                  ) : (
                    <>
                      {followupsError ? (
                        <div className='text-sm text-destructive'>
                          {followupsError.message}
                        </div>
                      ) : null}

                      <div className='overflow-auto rounded-lg border border-border bg-white'>
                        {followupsLoading ? (
                          <div className='flex h-40 items-center justify-center'>
                            <Loading />
                          </div>
                        ) : (
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>
                                  {t(
                                    'module.dashboard.detail.followUps.outline',
                                  )}
                                </TableHead>
                                <TableHead>
                                  {t(
                                    'module.dashboard.detail.followUps.askedAt',
                                  )}
                                </TableHead>
                                <TableHead>
                                  {t(
                                    'module.dashboard.detail.followUps.question',
                                  )}
                                </TableHead>
                                <TableHead>
                                  {t(
                                    'module.dashboard.detail.followUps.answer',
                                  )}
                                </TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {followups.length === 0 && (
                                <TableEmpty colSpan={4}>
                                  {t('module.dashboard.detail.followUps.empty')}
                                </TableEmpty>
                              )}
                              {followups.map(item => (
                                <TableRow
                                  key={`${item.outline_item_bid}-${item.asked_at}-${item.position}`}
                                >
                                  <TableCell className='min-w-[180px]'>
                                    <div className='text-sm text-foreground'>
                                      {item.outline_title ||
                                        item.outline_item_bid}
                                    </div>
                                    <div className='text-xs text-muted-foreground'>
                                      {item.position > 0
                                        ? `#${item.position}`
                                        : item.outline_item_bid}
                                    </div>
                                  </TableCell>
                                  <TableCell className='whitespace-nowrap'>
                                    {item.asked_at || '-'}
                                  </TableCell>
                                  <TableCell className='min-w-[240px]'>
                                    <div className='whitespace-pre-wrap break-words text-sm text-foreground'>
                                      {item.question || '-'}
                                    </div>
                                  </TableCell>
                                  <TableCell className='min-w-[240px]'>
                                    <div className='whitespace-pre-wrap break-words text-sm text-foreground'>
                                      {item.answer || '-'}
                                    </div>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        )}
                      </div>

                      <div className='flex justify-end'>
                        <Pagination className='justify-end w-auto mx-0'>
                          <PaginationContent>
                            <PaginationItem>
                              <PaginationPrevious
                                href='#'
                                onClick={event => {
                                  event.preventDefault();
                                  handleFollowupsPageChange(
                                    followupsPageIndex - 1,
                                  );
                                }}
                                aria-disabled={followupsPageIndex <= 1}
                                className={
                                  followupsPageIndex <= 1
                                    ? 'pointer-events-none opacity-50'
                                    : ''
                                }
                              >
                                {t('module.dashboard.pagination.prev')}
                              </PaginationPrevious>
                            </PaginationItem>

                            {followupsPages.map(page => (
                              <PaginationItem key={page}>
                                <PaginationLink
                                  href='#'
                                  onClick={event => {
                                    event.preventDefault();
                                    handleFollowupsPageChange(page);
                                  }}
                                  isActive={page === followupsPageIndex}
                                >
                                  {page}
                                </PaginationLink>
                              </PaginationItem>
                            ))}

                            <PaginationItem>
                              <PaginationNext
                                href='#'
                                onClick={event => {
                                  event.preventDefault();
                                  handleFollowupsPageChange(
                                    followupsPageIndex + 1,
                                  );
                                }}
                                aria-disabled={
                                  followupsPageIndex >= followupsPageCount
                                }
                                className={
                                  followupsPageIndex >= followupsPageCount
                                    ? 'pointer-events-none opacity-50'
                                    : ''
                                }
                              >
                                {t('module.dashboard.pagination.next')}
                              </PaginationNext>
                            </PaginationItem>
                          </PaginationContent>
                        </Pagination>
                      </div>
                    </>
                  )}
                </div>
              </TabsContent>

              <TabsContent value='profile'>
                <div className='overflow-auto rounded-lg border border-border bg-white'>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>
                          {t('module.dashboard.detail.personalization.key')}
                        </TableHead>
                        <TableHead>
                          {t('module.dashboard.detail.personalization.value')}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(detail?.variables || []).length === 0 && (
                        <TableEmpty colSpan={2}>
                          {t('module.dashboard.detail.personalization.empty')}
                        </TableEmpty>
                      )}
                      {(detail?.variables || []).map(item => (
                        <TableRow key={item.key}>
                          <TableCell className='whitespace-nowrap'>
                            {item.key}
                          </TableCell>
                          <TableCell>
                            <div className='whitespace-pre-wrap break-words text-sm text-foreground'>
                              {item.value || '-'}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>
            </Tabs>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
