'use client';

import { X } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
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
import { cn } from '@/lib/utils';
import type {
  DashboardCourseDetailLearnerItem,
  DashboardCourseDetailLearners,
} from '@/types/dashboard';

type ErrorState = { message: string; code?: number };
type LearnerFilterStatus = 'all' | 'not_started' | 'learning' | 'completed';

type DashboardCourseLearnersCardProps = {
  learners: DashboardCourseDetailLearners;
  loading: boolean;
  error: ErrorState | null;
  keyword: string;
  learningStatus: LearnerFilterStatus;
  lastLearningStart: string;
  lastLearningEnd: string;
  searchPlaceholder: string;
  emptyValue: string;
  onKeywordChange: (value: string) => void;
  onLearningStatusChange: (value: LearnerFilterStatus) => void;
  onLastLearningTimeChange: (range: { start: string; end: string }) => void;
  onSearch: () => void;
  onReset: () => void;
  onPageChange: (page: number) => void;
  onFollowUpClick: (learner: DashboardCourseDetailLearnerItem) => void;
};

const formatDateTime = (
  value: string,
  emptyValue: string,
  displayValue?: string,
): string => {
  if (displayValue) {
    return displayValue;
  }
  if (!value) {
    return emptyValue;
  }
  return value;
};

const formatLearningProgress = (
  learnedLessonCount: number,
  totalLessonCount: number,
): string => `${learnedLessonCount} / ${totalLessonCount}`;

const buildContactLine = (
  learner: DashboardCourseDetailLearnerItem,
  emptyValue: string,
): string => {
  const values = [learner.mobile, learner.email].filter(Boolean);
  if (values.length > 0) {
    return values.join(' / ');
  }
  return learner.user_bid || emptyValue;
};

const buildLearnerAccessibleLabel = (
  learner: DashboardCourseDetailLearnerItem,
): string =>
  learner.nickname || learner.mobile || learner.email || learner.user_bid;

function ClearableTextInput({
  value,
  placeholder,
  clearLabel,
  onChange,
  onSubmit,
}: {
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

export default function DashboardCourseLearnersCard({
  learners,
  loading,
  error,
  keyword,
  learningStatus,
  lastLearningStart,
  lastLearningEnd,
  searchPlaceholder,
  emptyValue,
  onKeywordChange,
  onLearningStatusChange,
  onLastLearningTimeChange,
  onSearch,
  onReset,
  onPageChange,
  onFollowUpClick,
}: DashboardCourseLearnersCardProps) {
  const { t } = useTranslation();

  const clearLabel = t('common.core.close');
  const statusOptions = useMemo(
    () => [
      {
        value: 'all' as const,
        label: t('module.dashboard.detail.learners.filters.statusAll'),
      },
      {
        value: 'not_started' as const,
        label: t('module.dashboard.detail.learners.status.notStarted'),
      },
      {
        value: 'learning' as const,
        label: t('module.dashboard.detail.learners.status.learning'),
      },
      {
        value: 'completed' as const,
        label: t('module.dashboard.detail.learners.status.completed'),
      },
    ],
    [t],
  );

  const resolveLearningStatusLabel = (learningStatusValue: string): string => {
    if (learningStatusValue === 'completed') {
      return t('module.dashboard.detail.learners.status.completed');
    }
    if (learningStatusValue === 'learning') {
      return t('module.dashboard.detail.learners.status.learning');
    }
    return t('module.dashboard.detail.learners.status.notStarted');
  };

  return (
    <Card className='overflow-hidden border-border/80 shadow-sm ring-1 ring-border/40'>
      <CardContent className='space-y-4 px-5 py-5'>
        <div className='space-y-1'>
          <h2 className='text-base font-semibold text-foreground'>
            {t('module.dashboard.detail.learners.title')}
          </h2>
        </div>

        <form
          className='rounded-xl border border-border bg-muted/20 p-3'
          onSubmit={event => {
            event.preventDefault();
            onSearch();
          }}
        >
          <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
            <div className='flex flex-col gap-2'>
              <label className='text-xs font-medium text-muted-foreground'>
                {t('module.dashboard.detail.learners.filters.userKeyword')}
              </label>
              <ClearableTextInput
                value={keyword}
                placeholder={searchPlaceholder}
                clearLabel={clearLabel}
                onChange={onKeywordChange}
                onSubmit={onSearch}
              />
            </div>
            <div className='flex flex-col gap-2'>
              <label className='text-xs font-medium text-muted-foreground'>
                {t('module.dashboard.detail.learners.filters.learningStatus')}
              </label>
              <Select
                value={learningStatus}
                onValueChange={value =>
                  onLearningStatusChange(value as LearnerFilterStatus)
                }
              >
                <SelectTrigger className='h-9'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {statusOptions.map(option => (
                    <SelectItem
                      key={option.value}
                      value={option.value}
                    >
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='flex flex-col gap-2'>
              <label className='text-xs font-medium text-muted-foreground'>
                {t('module.dashboard.detail.learners.filters.lastLearningTime')}
              </label>
              <AdminDateRangeFilter
                startValue={lastLearningStart}
                endValue={lastLearningEnd}
                triggerAriaLabel={t(
                  'module.dashboard.detail.learners.filters.lastLearningTime',
                )}
                placeholder={t(
                  'module.dashboard.detail.learners.filters.lastLearningTimePlaceholder',
                )}
                resetLabel={t('module.dashboard.entry.table.reset')}
                clearLabel={clearLabel}
                onChange={onLastLearningTimeChange}
              />
            </div>
          </div>

          <div className='mt-3 flex flex-col gap-3 md:flex-row md:items-end md:justify-between'>
            <div className='pl-1 text-sm text-muted-foreground md:pb-2'>
              {t('module.dashboard.detail.learners.totalCount', {
                count: learners.total,
              })}
            </div>
            <div className='flex items-center justify-start gap-2 md:justify-end'>
              <Button
                type='button'
                variant='outline'
                className='h-9 px-4'
                onClick={onReset}
                disabled={loading}
              >
                {t('module.dashboard.entry.table.reset')}
              </Button>
              <Button
                type='submit'
                className='h-9 px-4'
                disabled={loading}
              >
                {t('module.dashboard.entry.table.search')}
              </Button>
            </div>
          </div>
        </form>

        <AdminTableShell
          loading={loading}
          isEmpty={!error && learners.items.length === 0}
          emptyContent={t('module.dashboard.detail.learners.empty')}
          emptyColSpan={6}
          withTooltipProvider={!error}
          tableWrapperClassName='overflow-auto'
          loadingClassName='min-h-[220px]'
          footer={
            learners.page_count > 1 ? (
              <AdminPagination
                pageIndex={learners.page}
                pageCount={learners.page_count}
                onPageChange={onPageChange}
                prevLabel={t('module.dashboard.pagination.prev')}
                nextLabel={t('module.dashboard.pagination.next')}
                prevAriaLabel={t('module.dashboard.pagination.prev')}
                nextAriaLabel={t('module.dashboard.pagination.next')}
                className='mx-0 w-auto justify-end'
              />
            ) : null
          }
          table={
            error ? (
              <div className='flex min-h-[220px] items-center justify-center p-6 text-center'>
                <div className='space-y-2'>
                  <div className='text-sm font-medium text-destructive'>
                    {error.message}
                  </div>
                  {typeof error.code === 'number' ? (
                    <div className='text-xs text-muted-foreground'>
                      {error.code}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              emptyRow => (
                <Table className='min-w-[920px] table-auto'>
                  <TableHeader>
                    <TableRow>
                      <TableHead>
                        {t('module.dashboard.detail.learners.columns.name')}
                      </TableHead>
                      <TableHead>
                        {t('module.dashboard.detail.learners.columns.progress')}
                      </TableHead>
                      <TableHead>
                        {t('module.dashboard.detail.learners.columns.status')}
                      </TableHead>
                      <TableHead>
                        {t(
                          'module.dashboard.detail.learners.columns.questions',
                        )}
                      </TableHead>
                      <TableHead>
                        {t(
                          'module.dashboard.detail.learners.columns.lastLearningAt',
                        )}
                      </TableHead>
                      <TableHead>
                        {t('module.dashboard.detail.learners.columns.joinedAt')}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {emptyRow}
                    {learners.items.map(learner => (
                      <TableRow key={learner.user_bid}>
                        <TableCell className='min-w-[240px] align-top'>
                          <div className='space-y-1'>
                            <AdminTooltipText
                              text={
                                learner.nickname ||
                                learner.mobile ||
                                learner.email ||
                                learner.user_bid
                              }
                              emptyValue={emptyValue}
                              className='block max-w-[220px] font-medium text-foreground'
                            />
                            <AdminTooltipText
                              text={buildContactLine(learner, emptyValue)}
                              emptyValue={emptyValue}
                              className='block max-w-[220px] text-xs text-muted-foreground'
                            />
                          </div>
                        </TableCell>
                        <TableCell className='whitespace-nowrap font-medium tabular-nums text-foreground'>
                          {formatLearningProgress(
                            learner.learned_lesson_count,
                            learner.total_lesson_count,
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant='outline'
                            className='border-0 bg-transparent px-0 py-0 text-xs font-medium text-foreground shadow-none'
                          >
                            {resolveLearningStatusLabel(
                              learner.learning_status,
                            )}
                          </Badge>
                        </TableCell>
                        <TableCell className='whitespace-nowrap font-medium tabular-nums text-foreground'>
                          {learner.follow_up_count > 0 ? (
                            <Button
                              type='button'
                              variant='link'
                              className='h-auto px-0 py-0 font-medium tabular-nums'
                              aria-label={t(
                                'module.dashboard.detail.learners.viewFollowUpsForLearner',
                                {
                                  learner: buildLearnerAccessibleLabel(learner),
                                },
                              )}
                              onClick={() => onFollowUpClick(learner)}
                            >
                              {learner.follow_up_count}
                            </Button>
                          ) : (
                            learner.follow_up_count
                          )}
                        </TableCell>
                        <TableCell className='whitespace-nowrap text-xs text-muted-foreground'>
                          <AdminTooltipText
                            text={formatDateTime(
                              learner.last_learning_at,
                              emptyValue,
                              learner.last_learning_at_display,
                            )}
                            emptyValue={emptyValue}
                            className='block max-w-full tabular-nums'
                          />
                        </TableCell>
                        <TableCell className='whitespace-nowrap text-xs text-muted-foreground'>
                          <AdminTooltipText
                            text={formatDateTime(
                              learner.joined_at,
                              emptyValue,
                              learner.joined_at_display,
                            )}
                            emptyValue={emptyValue}
                            className='block max-w-full tabular-nums'
                          />
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
  );
}
