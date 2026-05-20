'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import { ClearableTextInput } from '@/app/admin/operations/orders/orderUiShared';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
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
  AdminOperationCourseCreditUsageFilters,
  AdminOperationCourseCreditUsageItem,
  AdminOperationCourseCreditUsageListResponse,
  AdminOperationCourseCreditUsageModeFilter,
} from '../operation-course-types';

type ErrorState = { message: string; code?: number };

type CreditUsageColumnKey =
  | 'createdAt'
  | 'account'
  | 'nickname'
  | 'mode'
  | 'chapter'
  | 'lesson'
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
  mode: 110,
  chapter: 160,
  lesson: 160,
  credits: 120,
  model: 220,
} as const;
const CREDIT_USAGE_COLUMN_KEYS = Object.keys(
  CREDIT_USAGE_COLUMN_DEFAULT_WIDTHS,
) as CreditUsageColumnKey[];
const FILTER_ALL_OPTION = 'all';

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
  onModeChange,
  onDateRangeChange,
  onSearch,
  onReset,
  onPageChange,
}: {
  filtersDraft: AdminOperationCourseCreditUsageFilters;
  data: AdminOperationCourseCreditUsageListResponse;
  loading: boolean;
  error: ErrorState | null;
  contactMode: ContactMode;
  defaultUserName: string;
  emptyValue: string;
  onKeywordChange: (value: string) => void;
  onModeChange: (value: AdminOperationCourseCreditUsageModeFilter) => void;
  onDateRangeChange: (value: { start: string; end: string }) => void;
  onSearch: () => void;
  onReset: () => void;
  onPageChange: (page: number) => void;
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
      mode: row => [resolveModeLabel(row.usage_mode)],
      chapter: row => [row.chapter_title || emptyValue],
      lesson: row => [row.lesson_title || emptyValue],
      credits: row => [String(row.consumed_credits || 0)],
      model: row => [resolveModelDisplay(row)],
    };
    const multiplierMap: Partial<Record<CreditUsageColumnKey, number>> = {
      createdAt: 5,
      account: 6,
      nickname: 6,
      mode: 5.5,
      chapter: 6,
      lesson: 6,
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

  return (
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
              <ClearableTextInput
                value={filtersDraft.keyword}
                placeholder={keywordPlaceholder}
                clearLabel={t('module.chat.lessonFeedbackClearInput')}
                onChange={onKeywordChange}
              />
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
                onChange={({ start, end }) => onDateRangeChange({ start, end })}
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
          emptyColSpan={8}
          withTooltipProvider={!error}
          tableWrapperClassName='overflow-auto'
          loadingClassName='min-h-[240px]'
          footer={
            pageCount > 1 ? (
              <AdminPagination
                pageIndex={currentPage}
                pageCount={pageCount}
                onPageChange={onPageChange}
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
              />
            ) : null
          }
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
  );
}
