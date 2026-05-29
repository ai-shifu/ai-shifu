import React from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import ErrorDisplay from '@/components/ErrorDisplay';
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type {
  AdminOperationCreditNotificationItem,
  AdminOperationCreditNotificationOverview,
} from '../operation-credit-notification-types';
import {
  ALL_OPTION_VALUE,
  EMPTY_LABEL,
  type ErrorState,
  type NotificationFilters,
  type NotificationOverviewCardKey,
  NOTIFICATION_DELIVERY_STATUSES,
  NOTIFICATION_SOURCE_TYPES,
  NOTIFICATION_SKIP_REASONS,
  NOTIFICATION_TYPES,
  resolveCreditNotificationErrorText,
  resolveNotificationDeliveryStatus,
  resolveNotificationSkipReason,
} from './creditNotificationUtils';
import { CreditNotificationDetailSheet } from './CreditNotificationDetailSheet';

const COLUMN_MIN_WIDTH = 90;
const COLUMN_MAX_WIDTH = 460;
const COLUMN_WIDTH_STORAGE_KEY = 'adminCreditNotificationColumnWidths';
const DEFAULT_COLUMN_WIDTHS = {
  createdAt: 180,
  notification: 190,
  status: 140,
  creator: 220,
  source: 220,
  error: 220,
  action: 120,
} as const;
type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;
const TABLE_CELL_CLASS =
  'border-r border-border px-3 py-2 align-middle last:border-r-0';
const TABLE_TEXT_CELL_CLASS =
  'overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis last:border-r-0';
const SELECT_ITEM_CLASS = 'pl-3 pr-8';
const SELECT_ITEM_INDICATOR_CLASS = 'left-auto right-2';
const TABLE_INLINE_ACTION_BUTTON_CLASS =
  'inline-flex h-8 items-center justify-center rounded-md px-2.5 text-sm font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2';

export function CreditNotificationRecordsTab({
  items,
  loading,
  error,
  total,
  overview,
  activeOverviewCardKey,
  pageIndex,
  pageCount,
  draftFilters,
  updateDraftFilter,
  searchRecords,
  resetRecords,
  applyOverviewFilter,
  clearOverviewFilter,
  handlePageChange,
  requeue,
  resolveDeliveryStatusLabel,
  resolveSkipReasonLabel,
  resolveTypeLabel,
}: {
  items: AdminOperationCreditNotificationItem[];
  loading: boolean;
  error: ErrorState | null;
  total: number;
  overview: AdminOperationCreditNotificationOverview;
  activeOverviewCardKey: NotificationOverviewCardKey | null;
  pageIndex: number;
  pageCount: number;
  draftFilters: NotificationFilters;
  updateDraftFilter: (field: keyof NotificationFilters, value: string) => void;
  searchRecords: () => void;
  resetRecords: () => void;
  applyOverviewFilter: (cardKey: NotificationOverviewCardKey) => void;
  clearOverviewFilter: () => void;
  handlePageChange: (nextPage: number) => void;
  requeue: (notificationBid: string) => void;
  resolveDeliveryStatusLabel: (value: string) => string;
  resolveSkipReasonLabel: (value: string) => string;
  resolveTypeLabel: (value: string) => string;
}) {
  const { t } = useTranslation();
  const { getColumnStyle, getResizeHandleProps } =
    useAdminResizableColumns<ColumnKey>({
      storageKey: COLUMN_WIDTH_STORAGE_KEY,
      defaultWidths: DEFAULT_COLUMN_WIDTHS,
      minWidth: COLUMN_MIN_WIDTH,
      maxWidth: COLUMN_MAX_WIDTH,
    });

  const renderTooltipText = React.useCallback(
    (
      text?: string | null,
      className?: string,
      displayText?: React.ReactNode,
    ) => (
      <AdminTooltipText
        text={text}
        displayText={displayText}
        emptyValue={EMPTY_LABEL}
        className={className}
      />
    ),
    [],
  );

  const renderResizeHandle = React.useCallback(
    (key: ColumnKey) => (
      <span
        className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
        {...getResizeHandleProps(key)}
      />
    ),
    [getResizeHandleProps],
  );

  const [filtersExpanded, setFiltersExpanded] = React.useState(false);
  const [detailNotificationBid, setDetailNotificationBid] = React.useState('');
  const clearLabel = t('common.core.close');

  const overviewItems = React.useMemo(
    () => [
      {
        key: 'total',
        label: t('module.operationsCreditNotifications.overview.total'),
        value: overview.total,
        tooltip: t(
          'module.operationsCreditNotifications.overview.totalTooltip',
        ),
        onClick: () => applyOverviewFilter('total'),
      },
      {
        key: 'pending',
        label: t('module.operationsCreditNotifications.overview.pending'),
        value: overview.pending,
        tooltip: t(
          'module.operationsCreditNotifications.overview.pendingTooltip',
        ),
        onClick: () => applyOverviewFilter('pending'),
      },
      {
        key: 'sent',
        label: t('module.operationsCreditNotifications.overview.sent'),
        value: overview.sent,
        tooltip: t('module.operationsCreditNotifications.overview.sentTooltip'),
        onClick: () => applyOverviewFilter('sent'),
      },
      {
        key: 'failed',
        label: t('module.operationsCreditNotifications.overview.failed'),
        value: overview.failed,
        tooltip: t(
          'module.operationsCreditNotifications.overview.failedTooltip',
        ),
        onClick: () => applyOverviewFilter('failed'),
      },
      {
        key: 'skipped',
        label: t('module.operationsCreditNotifications.overview.skipped'),
        value: overview.skipped,
        tooltip: t(
          'module.operationsCreditNotifications.overview.skippedTooltip',
        ),
        onClick: () => applyOverviewFilter('skipped'),
      },
    ],
    [applyOverviewFilter, overview, t],
  );

  const activeOverviewItem = React.useMemo(
    () =>
      activeOverviewCardKey
        ? overviewItems.find(item => item.key === activeOverviewCardKey) || null
        : null,
    [activeOverviewCardKey, overviewItems],
  );

  const renderTypeSelect = () => (
    <Select
      value={draftFilters.notification_type || ALL_OPTION_VALUE}
      onValueChange={value =>
        updateDraftFilter(
          'notification_type',
          value === ALL_OPTION_VALUE ? '' : value,
        )
      }
    >
      <SelectTrigger className='h-9'>
        <SelectValue
          placeholder={t(
            'module.operationsCreditNotifications.filters.notificationType',
          )}
        />
      </SelectTrigger>
      <SelectContent>
        <SelectItem
          value={ALL_OPTION_VALUE}
          className={SELECT_ITEM_CLASS}
          indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
        >
          {t('module.operationsCreditNotifications.filters.all')}
        </SelectItem>
        {NOTIFICATION_TYPES.map(type => (
          <SelectItem
            key={type}
            value={type}
            className={SELECT_ITEM_CLASS}
            indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
          >
            {resolveTypeLabel(type)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const renderStatusSelect = () => (
    <Select
      value={draftFilters.delivery_status || ALL_OPTION_VALUE}
      onValueChange={value => {
        const nextValue = value === ALL_OPTION_VALUE ? '' : value;
        updateDraftFilter('delivery_status', nextValue);
        if (nextValue !== 'not_sent') {
          updateDraftFilter('skip_reason', '');
        }
      }}
    >
      <SelectTrigger className='h-9'>
        <SelectValue
          placeholder={t('module.operationsCreditNotifications.filters.status')}
        />
      </SelectTrigger>
      <SelectContent>
        <SelectItem
          value={ALL_OPTION_VALUE}
          className={SELECT_ITEM_CLASS}
          indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
        >
          {t('module.operationsCreditNotifications.filters.all')}
        </SelectItem>
        {NOTIFICATION_DELIVERY_STATUSES.map(status => (
          <SelectItem
            key={status}
            value={status}
            className={SELECT_ITEM_CLASS}
            indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
          >
            {resolveDeliveryStatusLabel(status)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const renderSkipReasonSelect = () => (
    <Select
      value={draftFilters.skip_reason || ALL_OPTION_VALUE}
      onValueChange={value =>
        updateDraftFilter(
          'skip_reason',
          value === ALL_OPTION_VALUE ? '' : value,
        )
      }
    >
      <SelectTrigger className='h-9'>
        <SelectValue
          placeholder={t(
            'module.operationsCreditNotifications.filters.skipReason',
          )}
        />
      </SelectTrigger>
      <SelectContent>
        <SelectItem
          value={ALL_OPTION_VALUE}
          className={SELECT_ITEM_CLASS}
          indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
        >
          {t('module.operationsCreditNotifications.filters.all')}
        </SelectItem>
        {NOTIFICATION_SKIP_REASONS.map(reason => (
          <SelectItem
            key={reason}
            value={reason}
            className={SELECT_ITEM_CLASS}
            indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
          >
            {resolveSkipReasonLabel(reason)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const resolveSourceTypeLabel = (value: string) =>
    t(
      `module.operationsCreditNotifications.sourceType.${value}`,
      value || EMPTY_LABEL,
    );

  const renderSourceTypeSelect = () => (
    <Select
      value={draftFilters.source_type || ALL_OPTION_VALUE}
      onValueChange={value =>
        updateDraftFilter(
          'source_type',
          value === ALL_OPTION_VALUE ? '' : value,
        )
      }
    >
      <SelectTrigger className='h-9'>
        <SelectValue
          placeholder={t(
            'module.operationsCreditNotifications.filters.sourceType',
          )}
        />
      </SelectTrigger>
      <SelectContent>
        <SelectItem
          value={ALL_OPTION_VALUE}
          className={SELECT_ITEM_CLASS}
          indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
        >
          {t('module.operationsCreditNotifications.filters.all')}
        </SelectItem>
        {NOTIFICATION_SOURCE_TYPES.map(sourceType => (
          <SelectItem
            key={sourceType}
            value={sourceType}
            className={SELECT_ITEM_CLASS}
            indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
          >
            {resolveSourceTypeLabel(sourceType)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const renderCreatedAtRange = () => (
    <AdminDateRangeFilter
      startValue={draftFilters.start_time}
      endValue={draftFilters.end_time}
      onChange={range => {
        updateDraftFilter('start_time', range.start);
        updateDraftFilter('end_time', range.end);
      }}
      placeholder={t(
        'module.operationsCreditNotifications.filters.timeRangePlaceholder',
      )}
      resetLabel={t('module.operationsCreditNotifications.actions.reset')}
      clearLabel={clearLabel}
    />
  );

  const renderCreatorInput = () => (
    <AdminClearableInput
      value={draftFilters.creator_keyword}
      placeholder={t(
        'module.operationsCreditNotifications.filters.creatorPlaceholder',
      )}
      clearLabel={clearLabel}
      onChange={value => updateDraftFilter('creator_keyword', value)}
    />
  );

  const filterItems = [
    {
      key: 'notification_type',
      label: t('module.operationsCreditNotifications.filters.notificationType'),
      component: renderTypeSelect(),
    },
    {
      key: 'status',
      label: t('module.operationsCreditNotifications.filters.status'),
      component: renderStatusSelect(),
    },
    ...(draftFilters.delivery_status === 'not_sent'
      ? [
          {
            key: 'skip_reason',
            label: t('module.operationsCreditNotifications.filters.skipReason'),
            component: renderSkipReasonSelect(),
          },
        ]
      : []),
    {
      key: 'creator_keyword',
      label: t('module.operationsCreditNotifications.filters.creator'),
      component: renderCreatorInput(),
    },
    {
      key: 'source_type',
      label: t('module.operationsCreditNotifications.filters.sourceType'),
      component: renderSourceTypeSelect(),
    },
    {
      key: 'created_at',
      label: t('module.operationsCreditNotifications.filters.createdTime'),
      component: renderCreatedAtRange(),
    },
  ];

  const resolveReasonDisplay = React.useCallback(
    (item: AdminOperationCreditNotificationItem) => {
      const detail = resolveCreditNotificationErrorText(
        t,
        item.error_code,
        item.error_message,
      );
      const skipReason = resolveNotificationSkipReason(item);
      if (detail || !skipReason) {
        return detail;
      }
      return resolveSkipReasonLabel(skipReason);
    },
    [resolveSkipReasonLabel, t],
  );

  return (
    <div className='flex min-h-0 flex-col gap-4'>
      <TooltipProvider delayDuration={150}>
        <div className='grid gap-3 md:grid-cols-3 xl:grid-cols-5'>
          {overviewItems.map(item => (
            <div
              key={item.key}
              className='rounded-lg border border-border/70 bg-muted/20 p-4 transition-colors hover:border-primary/30 hover:bg-primary/[0.04]'
            >
              <div className='flex items-start justify-between gap-2'>
                <button
                  type='button'
                  aria-label={item.label}
                  className='group min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
                  onClick={item.onClick}
                >
                  <div className='text-sm text-muted-foreground'>
                    {item.label}
                  </div>
                  <div className='mt-3 text-2xl font-semibold text-foreground transition-colors group-hover:text-primary'>
                    {item.value}
                  </div>
                </button>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type='button'
                      aria-label={item.tooltip}
                      className='inline-flex h-4 w-4 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
                    >
                      <QuestionMarkCircleIcon className='h-4 w-4' />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent className='max-w-56 text-left leading-5'>
                    {item.tooltip}
                  </TooltipContent>
                </Tooltip>
              </div>
            </div>
          ))}
        </div>
      </TooltipProvider>

      <div className='rounded-xl border border-border bg-white p-4 shadow-sm transition-all'>
        <div className='space-y-4'>
          {activeOverviewItem ? (
            <div className='flex flex-wrap items-center gap-2'>
              <span className='text-sm text-muted-foreground'>
                {t(
                  'module.operationsCreditNotifications.overview.activeFilter',
                )}
              </span>
              <button
                type='button'
                aria-label={`${activeOverviewItem.label} ${clearLabel}`}
                className='inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-3 py-1 text-sm text-foreground transition-colors hover:bg-muted'
                onClick={clearOverviewFilter}
              >
                <span>{activeOverviewItem.label}</span>
                <X className='h-3.5 w-3.5' />
              </button>
            </div>
          ) : null}
          <AdminFilter
            items={filterItems}
            expanded={filtersExpanded}
            onExpandedChange={setFiltersExpanded}
            onReset={resetRecords}
            onSearch={searchRecords}
            resetLabel={t('module.operationsCreditNotifications.actions.reset')}
            searchLabel={t(
              'module.operationsCreditNotifications.actions.search',
            )}
            expandLabel={t('common.core.expand')}
            collapseLabel={t('common.core.collapse')}
            collapsedCount={3}
            className='bg-transparent'
            contentClassName='min-w-0'
            labelClassName='w-20 text-right'
            collapsedGridClassName='gap-x-5 xl:grid-cols-3'
            expandedGridClassName='gap-x-5 xl:grid-cols-3'
            labelColon
          />
        </div>
      </div>

      {error ? (
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
        />
      ) : null}

      <div className='text-sm text-muted-foreground'>
        {t('module.operationsCreditNotifications.records.totalCount', {
          count: total,
        })}
      </div>

      <AdminTableShell
        loading={loading}
        isEmpty={items.length === 0}
        emptyContent={t('module.operationsCreditNotifications.empty')}
        emptyColSpan={Object.keys(DEFAULT_COLUMN_WIDTHS).length}
        withTooltipProvider
        tableWrapperClassName='max-h-[calc(100vh-22rem)] overflow-auto'
        table={emptyRow => (
          <Table containerClassName='overflow-visible max-h-none'>
            <TableHeader>
              <TableRow>
                <TableHead
                  className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                  style={getColumnStyle('createdAt')}
                >
                  {t('module.operationsCreditNotifications.table.createdAt')}
                  {renderResizeHandle('createdAt')}
                </TableHead>
                <TableHead
                  className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                  style={getColumnStyle('notification')}
                >
                  {t('module.operationsCreditNotifications.table.notification')}
                  {renderResizeHandle('notification')}
                </TableHead>
                <TableHead
                  className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                  style={getColumnStyle('status')}
                >
                  {t('module.operationsCreditNotifications.table.status')}
                  {renderResizeHandle('status')}
                </TableHead>
                <TableHead
                  className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                  style={getColumnStyle('creator')}
                >
                  {t('module.operationsCreditNotifications.table.creator')}
                  {renderResizeHandle('creator')}
                </TableHead>
                <TableHead
                  className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                  style={getColumnStyle('source')}
                >
                  {t('module.operationsCreditNotifications.table.source')}
                  {renderResizeHandle('source')}
                </TableHead>
                <TableHead
                  className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                  style={getColumnStyle('error')}
                >
                  {t('module.operationsCreditNotifications.table.error')}
                  {renderResizeHandle('error')}
                </TableHead>
                <TableHead
                  className={getAdminStickyRightHeaderClass('text-center')}
                  style={getColumnStyle('action')}
                >
                  {t('module.operationsCreditNotifications.table.action')}
                  {renderResizeHandle('action')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {items.map(item => (
                <TableRow key={item.notification_bid}>
                  <TableCell
                    className={TABLE_TEXT_CELL_CLASS}
                    style={getColumnStyle('createdAt')}
                  >
                    {renderTooltipText(formatAdminUtcDateTime(item.created_at))}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('notification')}
                  >
                    <div className='text-center'>
                      {renderTooltipText(
                        resolveTypeLabel(item.notification_type),
                        'text-foreground',
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('status')}
                  >
                    <div className='text-center'>
                      {renderTooltipText(
                        resolveDeliveryStatusLabel(
                          resolveNotificationDeliveryStatus(item),
                        ),
                        'text-foreground',
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('creator')}
                  >
                    <div className='flex min-w-0 flex-col items-center gap-0.5 text-center leading-tight'>
                      {renderTooltipText(
                        item.mobile_snapshot,
                        'block max-w-full text-foreground',
                      )}
                      {item.creator_nickname ? (
                        renderTooltipText(
                          item.creator_nickname,
                          'block max-w-full text-xs text-muted-foreground',
                        )
                      ) : (
                        <span className='text-xs text-muted-foreground'>
                          {EMPTY_LABEL}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('source')}
                  >
                    <div className='text-center'>
                      {renderTooltipText(
                        resolveSourceTypeLabel(item.source_type),
                        'text-foreground',
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('error')}
                  >
                    <div className='text-center'>
                      {renderTooltipText(
                        resolveReasonDisplay(item),
                        'text-foreground',
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className={getAdminStickyRightCellClass(
                      'whitespace-nowrap px-3 py-2 text-center',
                    )}
                    style={getColumnStyle('action')}
                  >
                    <div className='flex justify-center'>
                      <AdminRowActions
                        label={t(
                          'module.operationsCreditNotifications.actions.more',
                        )}
                        className={TABLE_INLINE_ACTION_BUTTON_CLASS}
                        actions={[
                          {
                            key: 'detail',
                            label: t(
                              'module.operationsCreditNotifications.actions.detail',
                            ),
                            onClick: () =>
                              setDetailNotificationBid(item.notification_bid),
                          },
                          {
                            key: 'requeue',
                            label: t(
                              'module.operationsCreditNotifications.actions.requeue',
                            ),
                            hidden: item.status !== 'failed_provider',
                            onClick: () => requeue(item.notification_bid),
                          },
                        ]}
                      />
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        pagination={{
          pageIndex,
          pageCount,
          onPageChange: handlePageChange,
          prevLabel: t('module.order.paginationPrev'),
          nextLabel: t('module.order.paginationNext'),
          prevAriaLabel: t('module.order.paginationPrev'),
          nextAriaLabel: t('module.order.paginationNext'),
          hideWhenSinglePage: true,
        }}
        footerClassName='mt-3'
      />
      <CreditNotificationDetailSheet
        notificationBid={detailNotificationBid}
        open={Boolean(detailNotificationBid)}
        onOpenChange={open => {
          if (!open) {
            setDetailNotificationBid('');
          }
        }}
        resolveTypeLabel={resolveTypeLabel}
        resolveDeliveryStatusLabel={resolveDeliveryStatusLabel}
        resolveSkipReasonLabel={resolveSkipReasonLabel}
        resolveSourceTypeLabel={resolveSourceTypeLabel}
      />
    </div>
  );
}
