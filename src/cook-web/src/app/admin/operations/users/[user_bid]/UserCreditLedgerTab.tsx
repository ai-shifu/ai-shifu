'use client';

import { useTranslation } from 'react-i18next';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { formatAdminCredits } from '@/app/admin/lib/numberFormat';
import { ClearableTextInput } from '@/app/admin/operations/orders/orderUiShared';
import ErrorDisplay from '@/components/ErrorDisplay';
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
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { TooltipProvider } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type {
  AdminOperationUserCreditFilters,
  AdminOperationUserCreditGrantSourceFilter,
  AdminOperationUserCreditsResponse,
  AdminOperationUserCreditTypeFilter,
  AdminOperationUserCreditUsageModeFilter,
} from '../../operation-user-types';
import {
  FILTER_ALL_OPTION,
  sanitizeCreditFiltersByType,
} from './creditFilterUtils';
import { formatOperatorNaiveDateTime } from '../dateTime';

type ErrorState = { message: string; code?: number };

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

const CreditLedgerFilters = ({
  filtersDraft,
  loading,
  onChange,
  onSearch,
  onReset,
}: {
  filtersDraft: AdminOperationUserCreditFilters;
  loading: boolean;
  onChange: (filters: AdminOperationUserCreditFilters) => void;
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
        <div className='flex flex-col gap-2 xl:w-[240px] xl:flex-none'>
          <Label className='text-xs font-medium text-muted-foreground'>
            {tOperationsUsers('detail.creditLedgerFilters.type')}
          </Label>
          <Select
            value={filtersDraft.creditType}
            onValueChange={value =>
              onChange(
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
            <ClearableTextInput
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
          <div className='flex flex-1 flex-col gap-2'>
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
  loading,
  error,
  items,
  pageIndex,
  pageCount,
  emptyValue,
  onFiltersChange,
  onSearch,
  onReset,
  onPageChange,
  onRetry,
}: {
  filtersDraft: AdminOperationUserCreditFilters;
  loading: boolean;
  error: ErrorState | null;
  items: AdminOperationUserCreditsResponse['items'];
  pageIndex: number;
  pageCount: number;
  emptyValue: string;
  onFiltersChange: (filters: AdminOperationUserCreditFilters) => void;
  onSearch: () => void;
  onReset: () => void;
  onPageChange: (page: number) => void;
  onRetry: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');

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
      className='shadow-sm'
      data-testid='admin-operation-user-credit-ledger-card'
    >
      <CardContent className='space-y-4 pt-6'>
        <CreditLedgerFilters
          filtersDraft={filtersDraft}
          loading={loading}
          onChange={onFiltersChange}
          onSearch={onSearch}
          onReset={onReset}
        />
        <TooltipProvider delayDuration={150}>
          <div
            className='overflow-auto'
            data-testid='admin-operation-user-credit-ledger-scroll'
          >
            <Table className='table-fixed'>
              <colgroup>
                <col className='w-[16%]' />
                <col className='w-[13%]' />
                <col className='w-[12%]' />
                <col className='w-[10%]' />
                <col className='w-[11%]' />
                <col className='w-[14%]' />
                <col className='w-[24%]' />
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.createdAt')}
                  </TableHead>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.entryType')}
                  </TableHead>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.sourceType')}
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
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableEmpty colSpan={7}>
                    {tOperationsUsers('detail.loadingCredits')}
                  </TableEmpty>
                ) : items.length ? (
                  items.map(item => (
                    <TableRow key={item.ledger_bid}>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={formatOperatorNaiveDateTime(item.created_at)}
                          emptyValue={emptyValue}
                        />
                      </TableCell>
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
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={
                            item.amount === '' ||
                            item.amount === null ||
                            item.amount === undefined
                              ? ''
                              : formatAdminCredits(
                                  Number(item.amount),
                                  i18n.language,
                                )
                          }
                          emptyValue={emptyValue}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={
                            item.balance_after === '' ||
                            item.balance_after === null ||
                            item.balance_after === undefined
                              ? ''
                              : formatAdminCredits(
                                  Number(item.balance_after),
                                  i18n.language,
                                )
                          }
                          emptyValue={emptyValue}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={formatOperatorNaiveDateTime(item.expires_at)}
                          emptyValue={emptyValue}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={resolveCreditLedgerNote(item.note, emptyValue)}
                          emptyValue={emptyValue}
                        />
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableEmpty colSpan={7}>
                    {tOperationsUsers('detail.emptyCredits')}
                  </TableEmpty>
                )}
              </TableBody>
            </Table>
          </div>
        </TooltipProvider>

        {pageCount > 1 ? (
          <AdminPagination
            pageIndex={pageIndex}
            pageCount={pageCount}
            onPageChange={onPageChange}
            prevLabel={t('module.order.paginationPrev')}
            nextLabel={t('module.order.paginationNext')}
            prevAriaLabel={t('module.order.paginationPrevAriaLabel')}
            nextAriaLabel={t('module.order.paginationNextAriaLabel')}
            className='justify-end w-auto mx-0'
          />
        ) : null}
      </CardContent>
    </Card>
  );
}
