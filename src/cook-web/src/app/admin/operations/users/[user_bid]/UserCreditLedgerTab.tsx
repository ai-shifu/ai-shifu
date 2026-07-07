'use client';

import { useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { formatAdminCredits } from '@/app/admin/lib/numberFormat';
import ErrorDisplay from '@/components/ErrorDisplay';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import type {
  AdminOperationUserCreditFilters,
  AdminOperationUserCreditGrantSourceFilter,
  AdminOperationUserCreditUsageDetailResponse,
  AdminOperationUserCreditsResponse,
  AdminOperationUserCreditTypeFilter,
  AdminOperationUserCreditUsageModeFilter,
  AdminOperationUserCreditUsageSceneFilter,
} from '../../operation-user-types';
import {
  FILTER_ALL_OPTION,
  sanitizeCreditFiltersByType,
} from './creditFilterUtils';
import { formatOperatorUtcDateTime } from '../dateTime';

type ErrorState = { message: string; code?: number };

const CREDIT_USAGE_DETAIL_COLUMN_COUNT = {
  read: 5,
  listen: 6,
} as const;

type OperatorUsersTranslator = (
  key: string,
  options?: { defaultValue?: string },
) => string;

/**
 * t('module.operationsUser.detail.creditLedger')
 * t('module.operationsUser.detail.creditLedgerFilters.type')
 * t('module.operationsUser.detail.creditLedgerFilters.typeOptions.all')
 * t('module.operationsUser.detail.creditLedgerFilters.typeOptions.consume')
 * t('module.operationsUser.detail.creditLedgerFilters.typeOptions.grant')
 * t('module.operationsUser.detail.creditLedgerFilters.typeOptions.other')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSource')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.all')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.subscription')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.trial_subscription')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.topup')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.manual')
 * t('module.operationsUser.detail.creditLedgerFilters.course')
 * t('module.operationsUser.detail.creditLedgerFilters.coursePlaceholder')
 * t('module.operationsUser.detail.creditLedgerFilters.usageScene')
 * t('module.operationsUser.detail.creditLedgerFilters.usageSceneOptions.all')
 * t('module.operationsUser.detail.creditLedgerFilters.usageSceneOptions.learning')
 * t('module.operationsUser.detail.creditLedgerFilters.usageSceneOptions.preview')
 * t('module.operationsUser.detail.creditLedgerFilters.usageSceneOptions.debug')
 * t('module.operationsUser.detail.creditLedgerFilters.usageMode')
 * t('module.operationsUser.detail.creditLedgerFilters.usageModeOptions.all')
 * t('module.operationsUser.detail.creditLedgerFilters.usageModeOptions.learn')
 * t('module.operationsUser.detail.creditLedgerFilters.usageModeOptions.listen')
 * t('module.operationsUser.detail.creditLedgerFilters.usageModeOptions.ask')
 * t('module.operationsUser.detail.creditLedgerFilters.time')
 * t('module.operationsUser.detail.creditLedgerFilters.timePlaceholder')
 * t('module.operationsUser.detail.creditLedgerColumns.createdAt')
 * t('module.operationsUser.detail.creditLedgerColumns.entryType')
 * t('module.operationsUser.detail.creditLedgerColumns.sourceType')
 * t('module.operationsUser.detail.creditLedgerColumns.amount')
 * t('module.operationsUser.detail.creditLedgerColumns.balanceAfter')
 * t('module.operationsUser.detail.creditLedgerColumns.expiresAt')
 * t('module.operationsUser.detail.creditLedgerColumns.note')
 * t('module.operationsUser.detail.creditLedgerColumns.user')
 * t('module.operationsUser.detail.creditLedgerColumns.usageScene')
 * t('module.operationsUser.detail.creditLedgerColumns.usageMode')
 * t('module.operationsUser.detail.creditLedgerColumns.course')
 * t('module.operationsUser.detail.creditLedgerColumns.sectionChapter')
 * t('module.operationsUser.detail.creditLedgerColumns.consumedCredits')
 * t('module.operationsUser.detail.creditLedgerColumns.grantedCredits')
 * t('module.operationsUser.detail.creditUsageDetail.actions.open')
 * t('module.operationsUser.detail.creditUsageDetail.actions.openAriaLabel')
 * t('module.operationsUser.detail.creditUsageDetail.columns.consumedCredits')
 * t('module.operationsUser.detail.creditUsageDetail.columns.createdAt')
 * t('module.operationsUser.detail.creditUsageDetail.columns.inputTokens')
 * t('module.operationsUser.detail.creditUsageDetail.columns.outputSummary')
 * t('module.operationsUser.detail.creditUsageDetail.columns.outputTokens')
 * t('module.operationsUser.detail.creditUsageDetail.columns.ttsContent')
 * t('module.operationsUser.detail.creditUsageDetail.columns.ttsDuration')
 * t('module.operationsUser.detail.creditUsageDetail.columns.ttsSegmentCount')
 * t('module.operationsUser.detail.creditUsageDetail.columns.ttsWordCount')
 * t('module.operationsUser.detail.creditUsageDetail.empty')
 * t('module.operationsUser.detail.creditUsageDetail.error')
 * t('module.operationsUser.detail.creditUsageDetail.expand')
 * t('module.operationsUser.detail.creditUsageDetail.collapse')
 * t('module.operationsUser.detail.creditUsageDetail.durationMinutesSeconds')
 * t('module.operationsUser.detail.creditUsageDetail.durationSeconds')
 * t('module.operationsUser.detail.creditUsageDetail.loading')
 * t('module.operationsUser.detail.creditUsageDetail.title')
 * t('module.operationsUser.detail.creditUsageDetail.description')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.adjustment')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.consume')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.debug_consume')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.expire')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.gift_expire')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.gift_grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.hold')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.learning_consume')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.manual_credit')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.manual_debit')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.manual_grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.preview_consume')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.refund')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.refund_return')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.release')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.subscription_expire')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.subscription_grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.topup_expire')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.topup_grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.trial_subscription_grant')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.debug')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.gift')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.learning')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.manual')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.preview')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.refund')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.subscription')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.topup')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.trial_subscription')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.usage')
 * t('module.operationsUser.detail.creditLedgerUsageSceneLabels.debug')
 * t('module.operationsUser.detail.creditLedgerUsageSceneLabels.preview')
 * t('module.operationsUser.detail.creditLedgerUsageSceneLabels.learning')
 * t('module.operationsUser.detail.emptyCredits')
 * t('module.operationsUser.detail.loadingCredits')
 */

const resolveCreditLedgerLabel = (
  tOperationsUsers: OperatorUsersTranslator,
  type: 'creditLedgerTypeLabels' | 'creditLedgerSourceLabels',
  displayCode: string,
  fallbackCode: string,
  emptyValue: string,
): string => {
  const normalizedCode = displayCode.trim() || fallbackCode.trim();
  if (!normalizedCode) {
    return emptyValue;
  }
  return tOperationsUsers(`detail.${type}.${normalizedCode}`, {
    defaultValue: normalizedCode,
  });
};

const resolveCreditLedgerNote = (note: string, emptyValue: string): string => {
  const normalizedNote = note.trim();
  if (normalizedNote) {
    return normalizedNote;
  }
  return emptyValue;
};

const formatCreditAmount = (
  amount: string,
  locale: string,
  options?: { absolute?: boolean },
): string => {
  if (amount === '' || amount === null || amount === undefined) {
    return '';
  }
  const value = Number(amount);
  if (!Number.isFinite(value)) {
    return '';
  }
  return formatAdminCredits(
    options?.absolute ? Math.abs(value) : value,
    locale,
  );
};

const resolveUsageSceneLabel = (
  tOperationsUsers: OperatorUsersTranslator,
  usageScene: string,
  emptyValue: string,
): string => {
  const normalizedUsageScene = usageScene.trim();
  if (!normalizedUsageScene) {
    return emptyValue;
  }
  return tOperationsUsers(
    `detail.creditLedgerUsageSceneLabels.${normalizedUsageScene}`,
    {
      defaultValue: normalizedUsageScene,
    },
  );
};

const resolveUsageModeLabel = (
  tOperationsUsers: OperatorUsersTranslator,
  usageMode: string,
  emptyValue: string,
): string => {
  const normalizedUsageMode = usageMode.trim();
  if (!normalizedUsageMode) {
    return emptyValue;
  }
  return tOperationsUsers(
    `detail.creditLedgerFilters.usageModeOptions.${normalizedUsageMode}`,
    {
      defaultValue: normalizedUsageMode,
    },
  );
};

const resolveSectionChapterDisplay = (
  chapterTitle: string,
  lessonTitle: string,
  emptyValue: string,
): string => {
  const normalizedChapterTitle = chapterTitle.trim();
  const normalizedLessonTitle = lessonTitle.trim();
  if (normalizedChapterTitle && normalizedLessonTitle) {
    return `${normalizedLessonTitle} / ${normalizedChapterTitle}`;
  }
  return normalizedLessonTitle || normalizedChapterTitle || emptyValue;
};

const splitUserLabel = (userLabel: string, emptyValue: string) => {
  const normalizedLabel = userLabel.trim();
  if (!normalizedLabel || normalizedLabel === emptyValue) {
    return {
      primary: emptyValue,
      secondary: '',
      tooltip: emptyValue,
    };
  }
  const [primary = '', ...secondaryParts] = normalizedLabel
    .split(' / ')
    .map(value => value.trim())
    .filter(Boolean);
  const secondary = secondaryParts.join(' / ');
  return {
    primary: primary || normalizedLabel,
    secondary,
    tooltip: normalizedLabel,
  };
};

const ExpandableUsageContent = ({
  content,
  emptyValue,
  expandLabel,
  collapseLabel,
}: {
  content: string;
  emptyValue: string;
  expandLabel: string;
  collapseLabel: string;
}) => {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();
  const normalizedContent = content.trim();
  if (!normalizedContent) {
    return <span className='text-muted-foreground'>{emptyValue}</span>;
  }
  return (
    <div className='min-w-0 text-left'>
      <span
        id={contentId}
        className={cn(
          'align-middle text-foreground',
          expanded ? 'whitespace-pre-wrap break-words' : 'line-clamp-1',
        )}
        title={normalizedContent}
      >
        {normalizedContent}
      </span>
      <button
        type='button'
        aria-controls={contentId}
        aria-expanded={expanded}
        className='ml-1 align-middle text-xs font-medium text-primary hover:underline'
        onClick={() => setExpanded(value => !value)}
      >
        {expanded ? collapseLabel : expandLabel}
      </button>
    </div>
  );
};

const CreditUsageDetailDialog = ({
  open,
  detail,
  loading,
  error,
  emptyValue,
  onOpenChange,
}: {
  open: boolean;
  detail: AdminOperationUserCreditUsageDetailResponse | null;
  loading: boolean;
  error: ErrorState | null;
  emptyValue: string;
  onOpenChange: (open: boolean) => void;
}) => {
  const { i18n } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');
  const items = detail?.items || [];
  const isListenDetail = detail?.usage_mode === 'listen';
  const detailFirstMetricLabel = isListenDetail
    ? tOperationsUsers('detail.creditUsageDetail.columns.ttsWordCount')
    : tOperationsUsers('detail.creditUsageDetail.columns.inputTokens');
  const detailSecondMetricLabel = isListenDetail
    ? tOperationsUsers('detail.creditUsageDetail.columns.ttsDuration')
    : tOperationsUsers('detail.creditUsageDetail.columns.outputTokens');
  const detailSummaryLabel = isListenDetail
    ? tOperationsUsers('detail.creditUsageDetail.columns.ttsContent')
    : tOperationsUsers('detail.creditUsageDetail.columns.outputSummary');
  const formatDuration = (durationMs: number) => {
    const safeDuration = Math.max(Number(durationMs || 0), 0);
    if (!safeDuration) {
      return emptyValue;
    }
    const totalSeconds = Math.round(safeDuration / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    if (!minutes) {
      return tOperationsUsers('detail.creditUsageDetail.durationSeconds', {
        seconds,
      });
    }
    return tOperationsUsers('detail.creditUsageDetail.durationMinutesSeconds', {
      minutes,
      seconds,
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='max-h-[82vh] max-w-5xl overflow-hidden p-0'>
        <DialogHeader className='border-b px-6 py-4'>
          <DialogTitle>
            {tOperationsUsers('detail.creditUsageDetail.title')}
          </DialogTitle>
          <DialogDescription className='sr-only'>
            {tOperationsUsers('detail.creditUsageDetail.description')}
          </DialogDescription>
        </DialogHeader>
        <div className='space-y-3 overflow-auto px-6 pb-5'>
          {loading ? (
            <AdminTableShell
              loading
              isEmpty={false}
              loadingClassName='min-h-[220px]'
              table={<div />}
            />
          ) : error ? (
            <div className='flex min-h-[220px] items-center justify-center p-6 text-center'>
              <div className='text-sm font-medium text-destructive'>
                {error.message ||
                  tOperationsUsers('detail.creditUsageDetail.error')}
              </div>
            </div>
          ) : (
            <AdminTableShell
              loading={false}
              isEmpty={items.length === 0}
              emptyContent={tOperationsUsers('detail.creditUsageDetail.empty')}
              emptyColSpan={
                isListenDetail
                  ? CREDIT_USAGE_DETAIL_COLUMN_COUNT.listen
                  : CREDIT_USAGE_DETAIL_COLUMN_COUNT.read
              }
              withTooltipProvider={false}
              tableWrapperClassName='max-h-[52vh] overflow-auto'
              loadingClassName='min-h-[220px]'
              table={emptyRow => (
                <Table className='table-auto'>
                  <TableHeader>
                    <TableRow>
                      <TableHead className='h-10 w-[150px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                        {tOperationsUsers(
                          'detail.creditUsageDetail.columns.createdAt',
                        )}
                      </TableHead>
                      <TableHead className='h-10 w-[100px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                        {tOperationsUsers(
                          'detail.creditUsageDetail.columns.consumedCredits',
                        )}
                      </TableHead>
                      <TableHead className='h-10 w-[110px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                        {detailFirstMetricLabel}
                      </TableHead>
                      <TableHead className='h-10 w-[110px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                        {detailSecondMetricLabel}
                      </TableHead>
                      {isListenDetail ? (
                        <TableHead className='h-10 w-[100px] whitespace-nowrap bg-muted/80 text-center text-xs'>
                          {tOperationsUsers(
                            'detail.creditUsageDetail.columns.ttsSegmentCount',
                          )}
                        </TableHead>
                      ) : null}
                      <TableHead className='h-10 min-w-[520px] whitespace-nowrap bg-muted/80 text-left text-xs'>
                        {detailSummaryLabel}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {emptyRow}
                    {items.map(item => (
                      <TableRow
                        key={
                          item.usage_bid ||
                          `${item.created_at}-${item.consumed_credits}-${item.usage_units}`
                        }
                      >
                        <TableCell className='border-r border-border py-2.5 text-center text-xs text-muted-foreground/70'>
                          {formatOperatorUtcDateTime(item.created_at) ||
                            emptyValue}
                        </TableCell>
                        <TableCell className='border-r border-border py-2.5 text-center text-sm font-medium tabular-nums text-foreground'>
                          {formatCreditAmount(
                            item.consumed_credits,
                            i18n.language,
                            { absolute: true },
                          ) || emptyValue}
                        </TableCell>
                        <TableCell className='border-r border-border py-2.5 text-center text-sm tabular-nums text-foreground'>
                          {isListenDetail
                            ? (item.word_count ?? emptyValue)
                            : item.input_tokens}
                        </TableCell>
                        <TableCell className='border-r border-border py-2.5 text-center text-sm tabular-nums text-foreground'>
                          {isListenDetail
                            ? formatDuration(item.duration_ms)
                            : item.output_tokens}
                        </TableCell>
                        {isListenDetail ? (
                          <TableCell className='border-r border-border py-2.5 text-center text-sm tabular-nums text-foreground'>
                            {item.segment_count ?? emptyValue}
                          </TableCell>
                        ) : null}
                        <TableCell className='py-2.5 text-sm text-foreground'>
                          <ExpandableUsageContent
                            content={item.content}
                            emptyValue={emptyValue}
                            expandLabel={tOperationsUsers(
                              'detail.creditUsageDetail.expand',
                            )}
                            collapseLabel={tOperationsUsers(
                              'detail.creditUsageDetail.collapse',
                            )}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

const CreditLedgerFilters = ({
  filtersDraft,
  loading,
  onChange,
  onTypeChange,
  onSearch,
  onReset,
}: {
  filtersDraft: AdminOperationUserCreditFilters;
  loading: boolean;
  onChange: (filters: AdminOperationUserCreditFilters) => void;
  onTypeChange: (filters: AdminOperationUserCreditFilters) => void;
  onSearch: () => void;
  onReset: () => void;
}) => {
  const { t } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');
  const showGrantFilters = filtersDraft.creditType === 'grant';
  const showConsumeFilters = filtersDraft.creditType === 'consume';
  const showOtherFilters = filtersDraft.creditType === 'other';

  return (
    <form
      className='rounded-xl border border-border bg-muted/20 p-3'
      onSubmit={event => {
        event.preventDefault();
        onSearch();
      }}
    >
      <div className='flex flex-col gap-3 xl:flex-row xl:items-end'>
        <div className='flex flex-col gap-2 xl:w-[160px] xl:flex-none'>
          <Label className='text-xs font-medium text-muted-foreground'>
            {tOperationsUsers('detail.creditLedgerFilters.type')}
          </Label>
          <Select
            value={filtersDraft.creditType}
            onValueChange={value =>
              onTypeChange(
                sanitizeCreditFiltersByType({
                  ...filtersDraft,
                  creditType: value as AdminOperationUserCreditTypeFilter,
                }),
              )
            }
          >
            <SelectTrigger className='h-9'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={FILTER_ALL_OPTION}>
                {tOperationsUsers('detail.creditLedgerFilters.typeOptions.all')}
              </SelectItem>
              <SelectItem value='consume'>
                {tOperationsUsers(
                  'detail.creditLedgerFilters.typeOptions.consume',
                )}
              </SelectItem>
              <SelectItem value='grant'>
                {tOperationsUsers(
                  'detail.creditLedgerFilters.typeOptions.grant',
                )}
              </SelectItem>
              <SelectItem value='other'>
                {tOperationsUsers(
                  'detail.creditLedgerFilters.typeOptions.other',
                )}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {showGrantFilters ? (
          <div className='flex flex-1 flex-col gap-2'>
            <Label className='text-xs font-medium text-muted-foreground'>
              {tOperationsUsers('detail.creditLedgerFilters.grantSource')}
            </Label>
            <Select
              value={filtersDraft.grantSource}
              onValueChange={value =>
                onChange({
                  ...filtersDraft,
                  grantSource:
                    value as AdminOperationUserCreditGrantSourceFilter,
                })
              }
            >
              <SelectTrigger className='h-9'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={FILTER_ALL_OPTION}>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.grantSourceOptions.all',
                  )}
                </SelectItem>
                <SelectItem value='subscription'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.grantSourceOptions.subscription',
                  )}
                </SelectItem>
                <SelectItem value='topup'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.grantSourceOptions.topup',
                  )}
                </SelectItem>
                <SelectItem value='trial_subscription'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.grantSourceOptions.trial_subscription',
                  )}
                </SelectItem>
                <SelectItem value='manual'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.grantSourceOptions.manual',
                  )}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : null}

        {showConsumeFilters ? (
          <div className='flex flex-1 flex-col gap-2'>
            <Label className='text-xs font-medium text-muted-foreground'>
              {tOperationsUsers('detail.creditLedgerFilters.course')}
            </Label>
            <AdminClearableInput
              value={filtersDraft.courseQuery}
              placeholder={tOperationsUsers(
                'detail.creditLedgerFilters.coursePlaceholder',
              )}
              clearLabel={t('module.chat.lessonFeedbackClearInput')}
              onChange={value =>
                onChange({
                  ...filtersDraft,
                  courseQuery: value,
                })
              }
            />
          </div>
        ) : null}

        {showConsumeFilters ? (
          <div className='flex flex-col gap-2 xl:w-[160px] xl:flex-none'>
            <Label className='text-xs font-medium text-muted-foreground'>
              {tOperationsUsers('detail.creditLedgerFilters.usageScene')}
            </Label>
            <Select
              value={filtersDraft.usageScene}
              onValueChange={value =>
                onChange({
                  ...filtersDraft,
                  usageScene: value as AdminOperationUserCreditUsageSceneFilter,
                })
              }
            >
              <SelectTrigger className='h-9'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={FILTER_ALL_OPTION}>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.usageSceneOptions.all',
                  )}
                </SelectItem>
                <SelectItem value='learning'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.usageSceneOptions.learning',
                  )}
                </SelectItem>
                <SelectItem value='preview'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.usageSceneOptions.preview',
                  )}
                </SelectItem>
                <SelectItem value='debug'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.usageSceneOptions.debug',
                  )}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : null}

        {showConsumeFilters ? (
          <div className='flex flex-col gap-2 xl:w-[160px] xl:flex-none'>
            <Label className='text-xs font-medium text-muted-foreground'>
              {tOperationsUsers('detail.creditLedgerFilters.usageMode')}
            </Label>
            <Select
              value={filtersDraft.usageMode}
              onValueChange={value =>
                onChange({
                  ...filtersDraft,
                  usageMode: value as AdminOperationUserCreditUsageModeFilter,
                })
              }
            >
              <SelectTrigger className='h-9'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={FILTER_ALL_OPTION}>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.usageModeOptions.all',
                  )}
                </SelectItem>
                <SelectItem value='learn'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.usageModeOptions.learn',
                  )}
                </SelectItem>
                <SelectItem value='listen'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.usageModeOptions.listen',
                  )}
                </SelectItem>
                <SelectItem value='ask'>
                  {tOperationsUsers(
                    'detail.creditLedgerFilters.usageModeOptions.ask',
                  )}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : null}

        {showGrantFilters || showConsumeFilters || showOtherFilters ? (
          <div
            className={cn(
              'flex flex-1 flex-col gap-2',
              showOtherFilters && 'xl:w-[420px] xl:flex-none',
            )}
          >
            <Label className='text-xs font-medium text-muted-foreground'>
              {tOperationsUsers('detail.creditLedgerFilters.time')}
            </Label>
            <AdminDateRangeFilter
              startValue={filtersDraft.startTime}
              endValue={filtersDraft.endTime}
              triggerAriaLabel={tOperationsUsers(
                'detail.creditLedgerFilters.time',
              )}
              placeholder={tOperationsUsers(
                'detail.creditLedgerFilters.timePlaceholder',
              )}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('module.chat.lessonFeedbackClearInput')}
              onChange={({ start, end }) =>
                onChange({
                  ...filtersDraft,
                  startTime: start,
                  endTime: end,
                })
              }
            />
          </div>
        ) : null}

        <div className='flex min-h-9 shrink-0 items-center justify-start gap-2 xl:ml-auto xl:justify-end'>
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
    </form>
  );
};

export default function UserCreditLedgerTab({
  filtersDraft,
  activeCreditType,
  loading,
  error,
  items,
  pageIndex,
  pageCount,
  userLabel,
  emptyValue,
  onFiltersChange,
  onTypeChange,
  onSearch,
  onReset,
  onPageChange,
  onRetry,
  onCourseOpen,
  onUsageDetailLoad,
}: {
  filtersDraft: AdminOperationUserCreditFilters;
  activeCreditType: AdminOperationUserCreditFilters['creditType'];
  loading: boolean;
  error: ErrorState | null;
  items: AdminOperationUserCreditsResponse['items'];
  pageIndex: number;
  pageCount: number;
  userLabel: string;
  emptyValue: string;
  onFiltersChange: (filters: AdminOperationUserCreditFilters) => void;
  onTypeChange: (filters: AdminOperationUserCreditFilters) => void;
  onSearch: () => void;
  onReset: () => void;
  onPageChange: (page: number) => void;
  onRetry: () => void;
  onCourseOpen: (courseBid: string) => void;
  onUsageDetailLoad: (
    usageBid: string,
  ) => Promise<AdminOperationUserCreditUsageDetailResponse>;
}) {
  const { t, i18n } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');
  const isConsumeView = activeCreditType === 'consume';
  const isGrantView = activeCreditType === 'grant';
  const isOtherView = activeCreditType === 'other';
  const tableColumnCount = isConsumeView ? 9 : 7;
  const [usageDetailOpen, setUsageDetailOpen] = useState(false);
  const [usageDetailLoading, setUsageDetailLoading] = useState(false);
  const [usageDetailError, setUsageDetailError] = useState<ErrorState | null>(
    null,
  );
  const [usageDetail, setUsageDetail] =
    useState<AdminOperationUserCreditUsageDetailResponse | null>(null);
  const usageDetailCacheRef = useRef(
    new Map<string, AdminOperationUserCreditUsageDetailResponse>(),
  );
  const usageDetailRequestSeqRef = useRef(0);

  const handleUsageDetailOpen = async (usageBid: string) => {
    const normalizedUsageBid = usageBid.trim();
    if (!normalizedUsageBid) {
      return;
    }
    setUsageDetailOpen(true);
    setUsageDetailError(null);

    const requestSeq = usageDetailRequestSeqRef.current + 1;
    usageDetailRequestSeqRef.current = requestSeq;
    const cachedDetail = usageDetailCacheRef.current.get(normalizedUsageBid);
    if (cachedDetail) {
      setUsageDetail(cachedDetail);
      setUsageDetailLoading(false);
      return;
    }

    setUsageDetail(currentDetail =>
      currentDetail === null ? currentDetail : null,
    );
    setUsageDetailLoading(true);
    try {
      const detail = await onUsageDetailLoad(normalizedUsageBid);
      if (usageDetailRequestSeqRef.current !== requestSeq) {
        return;
      }
      usageDetailCacheRef.current.set(normalizedUsageBid, detail);
      setUsageDetail(detail);
    } catch (requestError) {
      if (usageDetailRequestSeqRef.current !== requestSeq) {
        return;
      }
      const resolvedError = requestError as ErrorState;
      setUsageDetailError({
        message:
          resolvedError.message ||
          tOperationsUsers('detail.creditUsageDetail.error'),
        code: resolvedError.code,
      });
    } finally {
      if (usageDetailRequestSeqRef.current === requestSeq) {
        setUsageDetailLoading(false);
      }
    }
  };

  const handleUsageDetailOpenChange = (open: boolean) => {
    if (!open) {
      usageDetailRequestSeqRef.current += 1;
    }
    setUsageDetailOpen(open);
  };

  const renderCreditAmountCell = (
    amount: string,
    options?: { absolute?: boolean },
  ) => (
    <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
      <AdminTooltipText
        text={formatCreditAmount(amount, i18n.language, options)}
        emptyValue={emptyValue}
      />
    </TableCell>
  );

  const renderBalanceCell = (balanceAfter: string) =>
    renderCreditAmountCell(balanceAfter);

  const renderUsageDetailCell = (
    item: AdminOperationUserCreditsResponse['items'][number],
  ) => (
    <TableCell className='whitespace-nowrap text-center'>
      {item.usage_bid ? (
        <Button
          type='button'
          variant='ghost'
          className='h-7 px-2 text-primary hover:text-primary'
          aria-label={tOperationsUsers(
            'detail.creditUsageDetail.actions.openAriaLabel',
          )}
          onClick={() => void handleUsageDetailOpen(item.usage_bid)}
        >
          {tOperationsUsers('detail.creditUsageDetail.actions.open')}
        </Button>
      ) : (
        <span className='text-muted-foreground'>{emptyValue}</span>
      )}
    </TableCell>
  );

  const renderCreatedAtCell = (createdAt: string) => (
    <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
      <AdminTooltipText
        text={formatOperatorUtcDateTime(createdAt)}
        emptyValue={emptyValue}
        alwaysShowTooltip
      />
    </TableCell>
  );

  const renderTypeCell = (
    item: AdminOperationUserCreditsResponse['items'][number],
  ) => (
    <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
      <AdminTooltipText
        text={resolveCreditLedgerLabel(
          tOperationsUsers,
          'creditLedgerTypeLabels',
          item.display_entry_type,
          item.entry_type,
          emptyValue,
        )}
        emptyValue={emptyValue}
      />
    </TableCell>
  );

  const renderSourceCell = (
    item: AdminOperationUserCreditsResponse['items'][number],
  ) => (
    <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
      <AdminTooltipText
        text={resolveCreditLedgerLabel(
          tOperationsUsers,
          'creditLedgerSourceLabels',
          item.display_source_type,
          item.source_type,
          emptyValue,
        )}
        emptyValue={emptyValue}
      />
    </TableCell>
  );

  const renderNoteCell = (note: string) => (
    <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
      <AdminTooltipText
        text={resolveCreditLedgerNote(note, emptyValue)}
        emptyValue={emptyValue}
      />
    </TableCell>
  );

  const renderUserCell = () => {
    const userParts = splitUserLabel(userLabel, emptyValue);
    return (
      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
        <div
          className='min-w-0'
          title={userParts.tooltip}
        >
          <div className='truncate text-sm font-medium text-foreground'>
            {userParts.primary}
          </div>
          {userParts.secondary ? (
            <div className='truncate text-xs text-muted-foreground'>
              {userParts.secondary}
            </div>
          ) : null}
        </div>
      </TableCell>
    );
  };

  const renderCourseCell = (
    courseBid: string,
    courseName: string,
    fallbackText?: string,
  ) => {
    const normalizedCourseBid = String(courseBid || '').trim();
    const displayText =
      String(courseName || '').trim() ||
      fallbackText?.trim() ||
      normalizedCourseBid;
    return (
      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
        {normalizedCourseBid ? (
          <Button
            type='button'
            variant='ghost'
            className='h-auto max-w-full px-1 py-0 text-primary hover:text-primary'
            onClick={() => onCourseOpen(normalizedCourseBid)}
          >
            <AdminTooltipText
              text={displayText}
              emptyValue={emptyValue}
            />
          </Button>
        ) : (
          <AdminTooltipText
            text={displayText || ''}
            emptyValue={emptyValue}
          />
        )}
      </TableCell>
    );
  };

  const renderRows = () => {
    if (loading) {
      return (
        <TableEmpty colSpan={tableColumnCount}>
          {tOperationsUsers('detail.loadingCredits')}
        </TableEmpty>
      );
    }

    if (!items.length) {
      return (
        <TableEmpty colSpan={tableColumnCount}>
          {tOperationsUsers('detail.emptyCredits')}
        </TableEmpty>
      );
    }

    if (isConsumeView) {
      return items.map(item => (
        <TableRow key={item.ledger_bid}>
          {renderCreatedAtCell(item.created_at)}
          {renderUserCell()}
          <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
            <AdminTooltipText
              text={resolveUsageSceneLabel(
                tOperationsUsers,
                item.usage_scene,
                emptyValue,
              )}
              emptyValue={emptyValue}
            />
          </TableCell>
          <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
            <AdminTooltipText
              text={resolveUsageModeLabel(
                tOperationsUsers,
                item.usage_mode,
                emptyValue,
              )}
              emptyValue={emptyValue}
            />
          </TableCell>
          {renderCourseCell(item.course_bid, item.course_name)}
          <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
            <AdminTooltipText
              text={resolveSectionChapterDisplay(
                item.chapter_title,
                item.lesson_title,
                emptyValue,
              )}
              emptyValue={emptyValue}
            />
          </TableCell>
          {renderCreditAmountCell(item.amount, { absolute: true })}
          {renderBalanceCell(item.balance_after)}
          {renderUsageDetailCell(item)}
        </TableRow>
      ));
    }

    if (isGrantView) {
      return items.map(item => (
        <TableRow key={item.ledger_bid}>
          {renderCreatedAtCell(item.created_at)}
          {renderTypeCell(item)}
          {renderSourceCell(item)}
          {renderCreditAmountCell(item.amount, { absolute: true })}
          {renderBalanceCell(item.balance_after)}
          <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
            <AdminTooltipText
              text={formatOperatorUtcDateTime(item.expires_at)}
              emptyValue={emptyValue}
            />
          </TableCell>
          {renderNoteCell(item.note)}
        </TableRow>
      ));
    }

    if (isOtherView) {
      return items.map(item => (
        <TableRow key={item.ledger_bid}>
          {renderCreatedAtCell(item.created_at)}
          {renderTypeCell(item)}
          {renderSourceCell(item)}
          {renderCreditAmountCell(item.amount)}
          {renderBalanceCell(item.balance_after)}
          <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
            <AdminTooltipText
              text={
                formatOperatorUtcDateTime(item.expires_at) ||
                formatOperatorUtcDateTime(item.consumable_from)
              }
              emptyValue={emptyValue}
            />
          </TableCell>
          {renderNoteCell(item.note)}
        </TableRow>
      ));
    }

    return items.map(item => (
      <TableRow key={item.ledger_bid}>
        {renderCreatedAtCell(item.created_at)}
        {renderTypeCell(item)}
        {renderSourceCell(item)}
        {renderCourseCell(item.course_bid, item.course_name)}
        {renderCreditAmountCell(item.amount)}
        {renderBalanceCell(item.balance_after)}
        {renderNoteCell(item.note)}
      </TableRow>
    ));
  };

  if (error) {
    return (
      <div className='rounded-xl border border-border bg-white p-4 shadow-sm'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={onRetry}
        />
      </div>
    );
  }

  return (
    <Card
      className='flex h-fit flex-none flex-col shadow-sm'
      data-testid='admin-operation-user-credit-ledger-card'
    >
      <CardContent className='flex flex-none flex-col gap-4 pt-6'>
        <CreditLedgerFilters
          filtersDraft={filtersDraft}
          loading={loading}
          onChange={onFiltersChange}
          onTypeChange={onTypeChange}
          onSearch={onSearch}
          onReset={onReset}
        />
        <AdminTableShell
          loading={loading}
          isEmpty={!items.length}
          emptyContent={tOperationsUsers('detail.emptyCredits')}
          emptyColSpan={tableColumnCount}
          withTooltipProvider
          containerClassName='h-fit flex-none'
          tableWrapperClassName='h-fit max-h-[calc(100vh-22rem)] overflow-auto'
          tableWrapperTestId='admin-operation-user-credit-ledger-scroll'
          loadingClassName='min-h-[220px]'
          pagination={{
            pageIndex,
            pageCount,
            onPageChange,
            prevLabel: t('module.order.paginationPrev'),
            nextLabel: t('module.order.paginationNext'),
            prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
            nextAriaLabel: t('module.order.paginationNextAriaLabel'),
            hideWhenSinglePage: true,
          }}
          footerClassName='mt-0'
          table={emptyRow => (
            <Table className='table-fixed'>
              <colgroup>
                {isConsumeView ? (
                  <>
                    <col className='w-[10%]' />
                    <col className='w-[16%]' />
                    <col className='w-[7%]' />
                    <col className='w-[7%]' />
                    <col className='w-[18%]' />
                    <col className='w-[13%]' />
                    <col className='w-[9%]' />
                    <col className='w-[11%]' />
                    <col className='w-[9%]' />
                  </>
                ) : isGrantView || isOtherView ? (
                  <>
                    <col className='w-[16%]' />
                    <col className='w-[13%]' />
                    <col className='w-[12%]' />
                    <col className='w-[11%]' />
                    <col className='w-[12%]' />
                    <col className='w-[14%]' />
                    <col className='w-[22%]' />
                  </>
                ) : (
                  <>
                    <col className='w-[16%]' />
                    <col className='w-[13%]' />
                    <col className='w-[12%]' />
                    <col className='w-[17%]' />
                    <col className='w-[10%]' />
                    <col className='w-[11%]' />
                    <col className='w-[21%]' />
                  </>
                )}
              </colgroup>
              <TableHeader>
                {isConsumeView ? (
                  <TableRow>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.createdAt')}
                    </TableHead>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.user')}
                    </TableHead>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.usageScene',
                      )}
                    </TableHead>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.usageMode')}
                    </TableHead>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.course')}
                    </TableHead>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.sectionChapter',
                      )}
                    </TableHead>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.consumedCredits',
                      )}
                    </TableHead>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.balanceAfter',
                      )}
                    </TableHead>
                    <TableHead className='whitespace-nowrap text-center'>
                      {tOperationsUsers(
                        'detail.creditUsageDetail.actions.open',
                      )}
                    </TableHead>
                  </TableRow>
                ) : isGrantView ? (
                  <TableRow>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.createdAt')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.entryType')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.sourceType',
                      )}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.grantedCredits',
                      )}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.balanceAfter',
                      )}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.expiresAt')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.note')}
                    </TableHead>
                  </TableRow>
                ) : isOtherView ? (
                  <TableRow>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.createdAt')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.entryType')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.sourceType',
                      )}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.amount')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.balanceAfter',
                      )}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.expiresAt')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.note')}
                    </TableHead>
                  </TableRow>
                ) : (
                  <TableRow>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.createdAt')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.entryType')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.sourceType',
                      )}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.course')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.amount')}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers(
                        'detail.creditLedgerColumns.balanceAfter',
                      )}
                    </TableHead>
                    <TableHead className='text-center'>
                      {tOperationsUsers('detail.creditLedgerColumns.note')}
                    </TableHead>
                  </TableRow>
                )}
              </TableHeader>
              <TableBody>{emptyRow ?? renderRows()}</TableBody>
            </Table>
          )}
        />
      </CardContent>
      <CreditUsageDetailDialog
        open={usageDetailOpen}
        detail={usageDetail}
        loading={usageDetailLoading}
        error={usageDetailError}
        emptyValue={emptyValue}
        onOpenChange={handleUsageDetailOpenChange}
      />
    </Card>
  );
}
