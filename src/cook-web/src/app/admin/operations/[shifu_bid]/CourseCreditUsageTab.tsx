'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Label } from '@/components/ui/Label';
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
import { ContactMode } from '@/lib/resolve-contact-mode';
import { cn } from '@/lib/utils';
import type {
  AdminOperationCourseCreditUsageDetailItem,
  AdminOperationCourseCreditUsageDetailListResponse,
  AdminOperationCourseCreditUsageFilters,
  AdminOperationCourseCreditUsageItem,
  AdminOperationCourseCreditUsageListResponse,
  AdminOperationCourseCreditUsageModeFilter,
  AdminOperationCourseCreditUsageSceneFilter,
} from '../operation-course-types';

type ErrorState = { message: string; code?: number };

type CreditUsageColumnKey =
  | 'createdAt'
  | 'account'
  | 'nickname'
  | 'scene'
  | 'mode'
  | 'chapter'
  | 'lesson'
  | 'usageCount'
  | 'credits'
  | 'model';

const CREDIT_USAGE_COLUMN_MIN_WIDTH = 80;
const CREDIT_USAGE_COLUMN_MAX_WIDTH = 360;
const CREDIT_USAGE_COLUMN_WIDTH_STORAGE_KEY =
  'adminOperationCourseCreditUsageColumnWidths';
const CREDIT_USAGE_COLUMN_DEFAULT_WIDTHS = {
  createdAt: 170,
  account: 170,
  nickname: 140,
  scene: 100,
  mode: 110,
  chapter: 160,
  lesson: 160,
  usageCount: 110,
  credits: 120,
  model: 220,
} as const;
const CREDIT_USAGE_COLUMN_KEYS = Object.keys(
  CREDIT_USAGE_COLUMN_DEFAULT_WIDTHS,
) as CreditUsageColumnKey[];
const CREDIT_USAGE_DETAIL_TABLE_COLUMN_COUNT = {
  read: 5,
  listen: 6,
} as const;
const FILTER_ALL_OPTION = 'all';
const EMPTY_CREDIT_USAGE_DETAIL_RESPONSE: AdminOperationCourseCreditUsageDetailListResponse =
  {
    items: [],
    page: 1,
    page_count: 0,
    page_size: 10,
    total: 0,
  };

function formatUnknownEnumLabel(label: string, rawValue?: string) {
  const normalizedValue = (rawValue || '').trim();
  if (!normalizedValue) {
    return label;
  }

  const wrapper = /[^\x00-\x7F]/.test(`${label}${normalizedValue}`)
    ? ['（', '）']
    : [' (', ')'];
  return `${label}${wrapper[0]}${normalizedValue}${wrapper[1]}`;
}

function estimateColumnWidth(text: string, multiplier = 7) {
  if (!text) {
    return CREDIT_USAGE_COLUMN_MIN_WIDTH;
  }
  return text.length * multiplier + 24;
}

export default function CourseCreditUsageTab({
  filtersDraft,
  data,
  loading,
  error,
  contactMode,
  defaultUserName,
  emptyValue,
  onKeywordChange,
  onSceneChange,
  onModeChange,
  onDateRangeChange,
  onSearch,
  onReset,
  onPageChange,
  onFetchDetails,
}: {
  filtersDraft: AdminOperationCourseCreditUsageFilters;
  data: AdminOperationCourseCreditUsageListResponse;
  loading: boolean;
  error: ErrorState | null;
  contactMode: ContactMode;
  defaultUserName: string;
  emptyValue: string;
  onKeywordChange: (value: string) => void;
  onSceneChange: (value: AdminOperationCourseCreditUsageSceneFilter) => void;
  onModeChange: (value: AdminOperationCourseCreditUsageModeFilter) => void;
  onDateRangeChange: (value: { start: string; end: string }) => void;
  onSearch: () => void;
  onReset: () => void;
  onPageChange: (page: number) => void;
  onFetchDetails: (
    row: AdminOperationCourseCreditUsageItem,
    page: number,
  ) => Promise<AdminOperationCourseCreditUsageDetailListResponse>;
}) {
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');
  const {
    setColumnWidths,
    getColumnStyle,
    getResizeHandleProps,
    isManualColumn,
    clampWidth,
  } = useAdminResizableColumns<CreditUsageColumnKey>({
    storageKey: CREDIT_USAGE_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: CREDIT_USAGE_COLUMN_DEFAULT_WIDTHS,
    minWidth: CREDIT_USAGE_COLUMN_MIN_WIDTH,
    maxWidth: CREDIT_USAGE_COLUMN_MAX_WIDTH,
  });

  const clearLabel = useMemo(
    () => t('module.chat.lessonFeedbackClearInput'),
    [t],
  );
  const [detailRow, setDetailRow] =
    useState<AdminOperationCourseCreditUsageItem | null>(null);
  const [detailPage, setDetailPage] = useState(1);
  const [detailData, setDetailData] =
    useState<AdminOperationCourseCreditUsageDetailListResponse>(
      EMPTY_CREDIT_USAGE_DETAIL_RESPONSE,
    );
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ErrorState | null>(null);
  const [expandedUsageBids, setExpandedUsageBids] = useState<Set<string>>(
    () => new Set(),
  );
  const rows = useMemo(() => data.items || [], [data.items]);
  const currentPage = data.page || 1;
  const pageCount = Math.max(data.page_count || 0, 1);
  const keywordPlaceholder = useMemo(
    () =>
      contactMode === 'email'
        ? tOperations('detail.creditUsage.filters.userKeywordPlaceholderEmail')
        : tOperations('detail.creditUsage.filters.userKeywordPlaceholderPhone'),
    [contactMode, tOperations],
  );
  const accountLabel = useMemo(
    () =>
      contactMode === 'email'
        ? tOperations('detail.usersTable.accountEmail')
        : tOperations('detail.usersTable.accountPhone'),
    [contactMode, tOperations],
  );

  const resolveAccount = useCallback(
    (row: AdminOperationCourseCreditUsageItem) => {
      const preferred = contactMode === 'email' ? row.email : row.mobile;
      return preferred || emptyValue;
    },
    [contactMode, emptyValue],
  );

  const resolveSceneLabel = useCallback(
    (scene?: string) => {
      if (scene === 'learning') {
        return tOperations('detail.creditUsage.scenes.learning');
      }
      if (scene === 'preview') {
        return tOperations('detail.creditUsage.scenes.preview');
      }
      if (scene === 'debug') {
        return tOperations('detail.creditUsage.scenes.debug');
      }
      return formatUnknownEnumLabel(
        tOperations('detail.creditUsage.scenes.unknown'),
        scene,
      );
    },
    [tOperations],
  );

  const resolveModeLabel = useCallback(
    (mode?: string) => {
      if (mode === 'learn') {
        return tOperations('detail.creditUsage.modes.learn');
      }
      if (mode === 'listen') {
        return tOperations('detail.creditUsage.modes.listen');
      }
      if (mode === 'ask') {
        return tOperations('detail.creditUsage.modes.ask');
      }
      if (mode === 'mixed') {
        return tOperations('detail.creditUsage.modes.mixed');
      }
      return formatUnknownEnumLabel(
        tOperations('detail.creditUsage.modes.unknown'),
        mode,
      );
    },
    [tOperations],
  );

  const resolveModelDisplay = useCallback(
    (row: AdminOperationCourseCreditUsageItem) => {
      const provider = row.provider?.trim() || '';
      const model = row.model?.trim() || '';
      const baseDisplay =
        provider && model ? `${provider} / ${model}` : provider || model || '';
      if (row.model_variant_count > 1 && baseDisplay) {
        return tOperations('detail.creditUsage.modelSummary.multiple', {
          model: baseDisplay,
          count: row.model_variant_count,
        });
      }
      return baseDisplay || emptyValue;
    },
    [emptyValue, tOperations],
  );

  const handleOpenDetails = useCallback(
    (row: AdminOperationCourseCreditUsageItem) => {
      setDetailRow(row);
      setDetailPage(1);
      setDetailData(EMPTY_CREDIT_USAGE_DETAIL_RESPONSE);
      setDetailError(null);
      setExpandedUsageBids(new Set());
    },
    [],
  );

  const handleDetailOpenChange = useCallback((open: boolean) => {
    if (open) {
      return;
    }
    setDetailRow(null);
    setDetailPage(1);
    setDetailData(EMPTY_CREDIT_USAGE_DETAIL_RESPONSE);
    setDetailError(null);
    setExpandedUsageBids(new Set());
  }, []);

  const toggleOutputExpanded = useCallback((usageBid: string) => {
    setExpandedUsageBids(prev => {
      const next = new Set(prev);
      if (next.has(usageBid)) {
        next.delete(usageBid);
      } else {
        next.add(usageBid);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (!detailRow) {
      return;
    }

    let isActive = true;
    setDetailLoading(true);
    setDetailError(null);
    onFetchDetails(detailRow, detailPage)
      .then(response => {
        if (!isActive) {
          return;
        }
        setDetailData({
          items: (response?.items || []).map(item => ({
            ...item,
            word_count: item.word_count || 0,
            duration_ms: item.duration_ms || 0,
            segment_count: item.segment_count || 0,
          })),
          page: response?.page || detailPage,
          page_count: response?.page_count || 0,
          page_size: response?.page_size || 10,
          total: response?.total || 0,
        });
      })
      .catch(err => {
        if (!isActive) {
          return;
        }
        setDetailData(EMPTY_CREDIT_USAGE_DETAIL_RESPONSE);
        setDetailError({
          message: err instanceof Error ? err.message : String(err),
        });
      })
      .finally(() => {
        if (isActive) {
          setDetailLoading(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [detailPage, detailRow, onFetchDetails]);

  useEffect(() => {
    if (!rows.length) {
      setColumnWidths(prev => {
        const next = { ...prev };
        CREDIT_USAGE_COLUMN_KEYS.forEach(key => {
          if (!isManualColumn(key)) {
            next[key] = CREDIT_USAGE_COLUMN_DEFAULT_WIDTHS[key];
          }
        });
        return next;
      });
      return;
    }

    const nextWidths: Partial<Record<CreditUsageColumnKey, number>> = {};
    const columnValueExtractors: Record<
      CreditUsageColumnKey,
      (row: AdminOperationCourseCreditUsageItem) => string[]
    > = {
      createdAt: row => [row.created_at || emptyValue],
      account: row => [resolveAccount(row)],
      nickname: row => [row.nickname || defaultUserName],
      scene: row => [resolveSceneLabel(row.usage_scene)],
      mode: row => [resolveModeLabel(row.usage_mode)],
      chapter: row => [row.chapter_title || emptyValue],
      lesson: row => [row.lesson_title || emptyValue],
      usageCount: row => [String(row.usage_count || 0)],
      credits: row => [String(row.consumed_credits || 0)],
      model: row => [resolveModelDisplay(row)],
    };
    const multiplierMap: Partial<Record<CreditUsageColumnKey, number>> = {
      createdAt: 5,
      account: 6,
      nickname: 6,
      scene: 5.5,
      mode: 5.5,
      chapter: 6,
      lesson: 6,
      usageCount: 5.5,
      credits: 5.5,
      model: 6,
    };

    rows.forEach(row => {
      CREDIT_USAGE_COLUMN_KEYS.forEach(key => {
        const texts = columnValueExtractors[key](row).filter(Boolean);
        if (!texts.length) {
          return;
        }
        const required = texts.reduce(
          (maxWidth, text) =>
            Math.max(
              maxWidth,
              estimateColumnWidth(text, multiplierMap[key] ?? 7),
            ),
          Number(CREDIT_USAGE_COLUMN_DEFAULT_WIDTHS[key]),
        );
        if (
          !nextWidths[key] ||
          required > (nextWidths[key] ?? CREDIT_USAGE_COLUMN_MIN_WIDTH)
        ) {
          nextWidths[key] = required;
        }
      });
    });

    setColumnWidths(prev => {
      const next = { ...prev };
      CREDIT_USAGE_COLUMN_KEYS.forEach(key => {
        if (!isManualColumn(key)) {
          next[key] = clampWidth(
            nextWidths[key] ?? CREDIT_USAGE_COLUMN_DEFAULT_WIDTHS[key],
          );
        }
      });
      return next;
    });
  }, [
    clampWidth,
    defaultUserName,
    emptyValue,
    isManualColumn,
    resolveAccount,
    resolveSceneLabel,
    resolveModeLabel,
    resolveModelDisplay,
    rows,
    setColumnWidths,
  ]);

  const renderResizeHandle = (key: CreditUsageColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getResizeHandleProps(key)}
    />
  );

  const renderOutputSummary = (
    detail: AdminOperationCourseCreditUsageDetailItem,
  ) => {
    const outputSummary = detail.output_summary?.trim() || '';
    if (!outputSummary || outputSummary === emptyValue) {
      return <span className='text-muted-foreground'>{emptyValue}</span>;
    }
    const isExpanded = expandedUsageBids.has(detail.usage_bid);
    return (
      <div className='min-w-0 text-left'>
        <span
          className={cn(
            'align-middle text-foreground',
            isExpanded
              ? 'whitespace-pre-wrap break-words'
              : 'inline-block max-w-[360px] truncate align-bottom',
          )}
        >
          {outputSummary}
        </span>
        <button
          type='button'
          className='ml-1 align-middle text-xs font-medium text-primary hover:underline'
          onClick={() => toggleOutputExpanded(detail.usage_bid)}
        >
          {isExpanded
            ? tOperations('detail.creditUsage.details.collapse')
            : tOperations('detail.creditUsage.details.expand')}
        </button>
      </div>
    );
  };
  const isListenDetail = detailRow?.usage_mode === 'listen';
  const detailFirstMetricLabel = isListenDetail
    ? tOperations('detail.creditUsage.details.table.ttsWordCount')
    : tOperations('detail.creditUsage.details.table.inputTokens');
  const detailSecondMetricLabel = isListenDetail
    ? tOperations('detail.creditUsage.details.table.ttsDuration')
    : tOperations('detail.creditUsage.details.table.outputTokens');
  const detailSummaryLabel = isListenDetail
    ? tOperations('detail.creditUsage.details.table.ttsContent')
    : tOperations('detail.creditUsage.details.table.outputSummary');
  const formatDuration = (durationMs: number) => {
    const safeDuration = Math.max(Number(durationMs || 0), 0);
    if (!safeDuration) {
      return emptyValue;
    }
    const totalSeconds = Math.round(safeDuration / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    if (!minutes) {
      return tOperations('detail.creditUsage.details.durationSeconds', {
        seconds,
      });
    }
    return tOperations('detail.creditUsage.details.durationMinutesSeconds', {
      minutes,
      seconds: String(seconds).padStart(2, '0'),
    });
  };

  return (
    <>
      <Card className='overflow-hidden border-border/80 shadow-sm ring-1 ring-border/40'>
        <CardContent className='space-y-3 px-6 py-6'>
          <form
            className='rounded-xl border border-border bg-muted/20 p-3'
            onSubmit={event => {
              event.preventDefault();
              onSearch();
            }}
          >
            <div className='flex flex-col gap-3 xl:flex-row xl:items-end'>
              <div className='flex flex-1 flex-col gap-2'>
                <Label className='text-xs font-medium text-muted-foreground'>
                  {tOperations('detail.creditUsage.filters.userKeyword')}
                </Label>
                <AdminClearableInput
                  value={filtersDraft.keyword}
                  placeholder={keywordPlaceholder}
                  clearLabel={t('module.chat.lessonFeedbackClearInput')}
                  onChange={onKeywordChange}
                />
              </div>
              <div className='flex flex-1 flex-col gap-2'>
                <Label className='text-xs font-medium text-muted-foreground'>
                  {tOperations('detail.creditUsage.filters.scene')}
                </Label>
                <Select
                  value={filtersDraft.usageScene}
                  onValueChange={value =>
                    onSceneChange(
                      value as AdminOperationCourseCreditUsageSceneFilter,
                    )
                  }
                >
                  <SelectTrigger className='h-9'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={FILTER_ALL_OPTION}>
                      {tOperations('detail.creditUsage.filters.sceneAll')}
                    </SelectItem>
                    <SelectItem value='learning'>
                      {tOperations('detail.creditUsage.scenes.learning')}
                    </SelectItem>
                    <SelectItem value='preview'>
                      {tOperations('detail.creditUsage.scenes.preview')}
                    </SelectItem>
                    <SelectItem value='debug'>
                      {tOperations('detail.creditUsage.scenes.debug')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className='flex flex-1 flex-col gap-2'>
                <Label className='text-xs font-medium text-muted-foreground'>
                  {tOperations('detail.creditUsage.filters.mode')}
                </Label>
                <Select
                  value={filtersDraft.mode}
                  onValueChange={value =>
                    onModeChange(
                      value as AdminOperationCourseCreditUsageModeFilter,
                    )
                  }
                >
                  <SelectTrigger className='h-9'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={FILTER_ALL_OPTION}>
                      {tOperations('detail.creditUsage.filters.modeAll')}
                    </SelectItem>
                    <SelectItem value='learn'>
                      {tOperations('detail.creditUsage.modes.learn')}
                    </SelectItem>
                    <SelectItem value='listen'>
                      {tOperations('detail.creditUsage.modes.listen')}
                    </SelectItem>
                    <SelectItem value='ask'>
                      {tOperations('detail.creditUsage.modes.ask')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className='flex flex-1 flex-col gap-2'>
                <Label className='text-xs font-medium text-muted-foreground'>
                  {tOperations('detail.creditUsage.filters.time')}
                </Label>
                <AdminDateRangeFilter
                  startValue={filtersDraft.startTime}
                  endValue={filtersDraft.endTime}
                  triggerAriaLabel={tOperations(
                    'detail.creditUsage.filters.time',
                  )}
                  placeholder={tOperations(
                    'detail.creditUsage.filters.timePlaceholder',
                  )}
                  resetLabel={tOperations('detail.creditUsage.filters.reset')}
                  clearLabel={clearLabel}
                  onChange={({ start, end }) =>
                    onDateRangeChange({ start, end })
                  }
                />
              </div>
              <div className='flex min-h-9 shrink-0 items-center justify-start gap-2 xl:justify-end'>
                <Button
                  type='button'
                  variant='outline'
                  className='h-9 px-4'
                  onClick={onReset}
                  disabled={loading}
                >
                  {t('module.order.filters.reset')}
                </Button>
                <Button
                  type='submit'
                  className='h-9 px-4'
                  disabled={loading}
                >
                  {t('module.order.filters.search')}
                </Button>
              </div>
            </div>
            <div className='mt-3 pl-3 text-sm text-muted-foreground'>
              {tOperations('detail.creditUsage.count', {
                count: data.total,
              })}
            </div>
          </form>

          <AdminTableShell
            loading={loading}
            isEmpty={!error && rows.length === 0}
            emptyContent={tOperations('detail.creditUsage.table.empty')}
            emptyColSpan={
              Object.keys(CREDIT_USAGE_COLUMN_DEFAULT_WIDTHS).length
            }
            withTooltipProvider={!error}
            tableWrapperClassName='overflow-auto'
            loadingClassName='min-h-[240px]'
            pagination={{
              pageIndex: currentPage,
              pageCount,
              onPageChange,
              prevLabel: t('module.order.paginationPrev'),
              nextLabel: t('module.order.paginationNext'),
              prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
              nextAriaLabel: t('module.order.paginationNextAriaLabel'),
              hideWhenSinglePage: true,
            }}
            table={
              error ? (
                <div className='flex min-h-[240px] items-center justify-center p-6 text-center'>
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
                          {tOperations('detail.creditUsage.table.createdAt')}
                          {renderResizeHandle('createdAt')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('account')}
                        >
                          {accountLabel}
                          {renderResizeHandle('account')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('nickname')}
                        >
                          {tOperations('detail.creditUsage.table.nickname')}
                          {renderResizeHandle('nickname')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('scene')}
                        >
                          {tOperations('detail.creditUsage.table.scene')}
                          {renderResizeHandle('scene')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('mode')}
                        >
                          {tOperations('detail.creditUsage.table.mode')}
                          {renderResizeHandle('mode')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('chapter')}
                        >
                          {tOperations('detail.creditUsage.table.chapter')}
                          {renderResizeHandle('chapter')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('lesson')}
                        >
                          {tOperations('detail.creditUsage.table.lesson')}
                          {renderResizeHandle('lesson')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('usageCount')}
                        >
                          {tOperations('detail.creditUsage.table.usageCount')}
                          {renderResizeHandle('usageCount')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('credits')}
                        >
                          {tOperations('detail.creditUsage.table.credits')}
                          {renderResizeHandle('credits')}
                        </TableHead>
                        <TableHead
                          className={cn(
                            ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
                            'h-10 whitespace-nowrap bg-muted/80 text-xs',
                          )}
                          style={getColumnStyle('model')}
                        >
                          {tOperations('detail.creditUsage.table.model')}
                          {renderResizeHandle('model')}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {emptyRow}
                      {rows.map(row => (
                        <TableRow key={row.group_key || row.usage_bid}>
                          <TableCell
                            className='py-2.5 border-r border-border text-center text-xs text-muted-foreground/65 last:border-r-0'
                            style={getColumnStyle('createdAt')}
                          >
                            <AdminTooltipText
                              text={formatAdminUtcDateTime(row.created_at)}
                              emptyValue={emptyValue}
                              className='mx-auto block max-w-full tabular-nums'
                            />
                          </TableCell>
                          <TableCell
                            className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                            style={getColumnStyle('account')}
                          >
                            <AdminTooltipText
                              text={resolveAccount(row)}
                              emptyValue={emptyValue}
                              className='mx-auto block max-w-[180px] text-foreground'
                            />
                          </TableCell>
                          <TableCell
                            className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                            style={getColumnStyle('nickname')}
                          >
                            <AdminTooltipText
                              text={row.nickname || defaultUserName}
                              emptyValue={emptyValue}
                              className='mx-auto block max-w-[140px]'
                            />
                          </TableCell>
                          <TableCell
                            className='py-2.5 border-r border-border text-center last:border-r-0'
                            style={getColumnStyle('scene')}
                          >
                            <Badge
                              variant='outline'
                              className='border-0 bg-transparent px-0 py-0 text-xs font-medium text-foreground shadow-none'
                            >
                              {resolveSceneLabel(row.usage_scene)}
                            </Badge>
                          </TableCell>
                          <TableCell
                            className='py-2.5 border-r border-border text-center last:border-r-0'
                            style={getColumnStyle('mode')}
                          >
                            <Badge
                              variant='outline'
                              className='border-0 bg-transparent px-0 py-0 text-xs font-medium text-foreground shadow-none'
                            >
                              {resolveModeLabel(row.usage_mode)}
                            </Badge>
                          </TableCell>
                          <TableCell
                            className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                            style={getColumnStyle('chapter')}
                          >
                            <AdminTooltipText
                              text={row.chapter_title}
                              emptyValue={emptyValue}
                              className='mx-auto block max-w-[180px]'
                            />
                          </TableCell>
                          <TableCell
                            className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                            style={getColumnStyle('lesson')}
                          >
                            <AdminTooltipText
                              text={row.lesson_title}
                              emptyValue={emptyValue}
                              className='mx-auto block max-w-[180px]'
                            />
                          </TableCell>
                          <TableCell
                            className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                            style={getColumnStyle('usageCount')}
                          >
                            <button
                              type='button'
                              className='tabular-nums text-primary hover:underline disabled:pointer-events-none disabled:text-foreground'
                              disabled={!row.usage_count}
                              aria-label={tOperations(
                                'detail.creditUsage.details.openUsageDetails',
                                { count: row.usage_count || 0 },
                              )}
                              onClick={() => handleOpenDetails(row)}
                            >
                              {row.usage_count}
                            </button>
                          </TableCell>
                          <TableCell
                            className='py-2.5 border-r border-border text-center text-sm text-foreground last:border-r-0'
                            style={getColumnStyle('credits')}
                          >
                            <span className='font-medium tabular-nums text-foreground'>
                              {row.consumed_credits}
                            </span>
                          </TableCell>
                          <TableCell
                            className='py-2.5 text-center text-sm text-foreground'
                            style={getColumnStyle('model')}
                          >
                            <AdminTooltipText
                              text={resolveModelDisplay(row)}
                              emptyValue={emptyValue}
                              className='mx-auto block max-w-[220px]'
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

      <Dialog
        open={Boolean(detailRow)}
        onOpenChange={handleDetailOpenChange}
      >
        <DialogContent className='max-h-[82vh] max-w-5xl overflow-hidden p-0'>
          <DialogHeader className='border-b px-6 py-4'>
            <DialogTitle>
              {tOperations('detail.creditUsage.details.title')}
            </DialogTitle>
          </DialogHeader>
          <div className='space-y-3 overflow-auto px-6 pb-5'>
            <AdminTableShell
              loading={detailLoading}
              isEmpty={!detailError && detailData.items.length === 0}
              emptyContent={tOperations('detail.creditUsage.details.empty')}
              emptyColSpan={
                isListenDetail
                  ? CREDIT_USAGE_DETAIL_TABLE_COLUMN_COUNT.listen
                  : CREDIT_USAGE_DETAIL_TABLE_COLUMN_COUNT.read
              }
              withTooltipProvider={false}
              tableWrapperClassName='max-h-[52vh] overflow-auto'
              loadingClassName='min-h-[220px]'
              pagination={{
                pageIndex: detailData.page || 1,
                pageCount: Math.max(detailData.page_count || 0, 1),
                onPageChange: setDetailPage,
                prevLabel: t('module.order.paginationPrev'),
                nextLabel: t('module.order.paginationNext'),
                prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
                nextAriaLabel: t('module.order.paginationNextAriaLabel'),
                hideWhenSinglePage: true,
              }}
              table={
                detailError ? (
                  <div className='flex min-h-[220px] items-center justify-center p-6 text-center'>
                    <div className='text-sm font-medium text-destructive'>
                      {detailError.message}
                    </div>
                  </div>
                ) : (
                  emptyRow => (
                    <Table className='table-auto'>
                      <TableHeader>
                        <TableRow>
                          <TableHead className='h-10 w-[170px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                            {tOperations(
                              'detail.creditUsage.details.table.createdAt',
                            )}
                          </TableHead>
                          <TableHead className='h-10 w-[120px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                            {tOperations(
                              'detail.creditUsage.details.table.credits',
                            )}
                          </TableHead>
                          <TableHead className='h-10 w-[120px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                            {detailFirstMetricLabel}
                          </TableHead>
                          <TableHead className='h-10 w-[120px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                            {detailSecondMetricLabel}
                          </TableHead>
                          {isListenDetail ? (
                            <TableHead className='h-10 w-[120px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                              {tOperations(
                                'detail.creditUsage.details.table.ttsSegmentCount',
                              )}
                            </TableHead>
                          ) : null}
                          <TableHead className='h-10 min-w-[360px] whitespace-nowrap bg-muted/80 text-left text-xs'>
                            {detailSummaryLabel}
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {emptyRow}
                        {detailData.items.map(detail => (
                          <TableRow key={detail.usage_bid}>
                            <TableCell className='border-r border-border py-2.5 text-center text-xs text-muted-foreground/70'>
                              {formatAdminUtcDateTime(detail.created_at) ||
                                emptyValue}
                            </TableCell>
                            <TableCell className='border-r border-border py-2.5 text-center text-sm font-medium tabular-nums text-foreground'>
                              {detail.consumed_credits}
                            </TableCell>
                            <TableCell className='border-r border-border py-2.5 text-center text-sm tabular-nums text-foreground'>
                              {isListenDetail
                                ? (detail.word_count ?? emptyValue)
                                : detail.input_tokens}
                            </TableCell>
                            <TableCell className='border-r border-border py-2.5 text-center text-sm tabular-nums text-foreground'>
                              {isListenDetail
                                ? formatDuration(detail.duration_ms)
                                : detail.output_tokens}
                            </TableCell>
                            {isListenDetail ? (
                              <TableCell className='border-r border-border py-2.5 text-center text-sm tabular-nums text-foreground'>
                                {detail.segment_count ?? emptyValue}
                              </TableCell>
                            ) : null}
                            <TableCell className='py-2.5 text-sm text-foreground'>
                              {renderOutputSummary(detail)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )
                )
              }
            />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
