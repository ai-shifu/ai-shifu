import React from 'react';
import { useTranslation } from 'react-i18next';
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import type {
  AdminOperationCreditNotificationItem,
  AdminOperationCreditNotificationOverview,
} from '../operation-credit-notification-types';
import {
  EMPTY_LABEL,
  type ErrorState,
  type NotificationFilters,
  type NotificationOverviewCardKey,
  resolveCreditNotificationErrorText,
  resolveNotificationDeliveryStatus,
  resolveNotificationSkipReason,
} from './creditNotificationUtils';
import { CreditNotificationDetailSheet } from './CreditNotificationDetailSheet';
import { CreditNotificationOverviewCards } from './CreditNotificationOverviewCards';
import { CreditNotificationRecordsFilter } from './CreditNotificationRecordsFilter';

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

  const [detailNotificationBid, setDetailNotificationBid] = React.useState('');

  const activeOverviewItem = React.useMemo(
    () =>
      activeOverviewCardKey
        ? (
            {
              total: t('module.operationsCreditNotifications.overview.total'),
              pending: t(
                'module.operationsCreditNotifications.overview.pending',
              ),
              sent: t('module.operationsCreditNotifications.overview.sent'),
              failed: t('module.operationsCreditNotifications.overview.failed'),
              skipped: t(
                'module.operationsCreditNotifications.overview.skipped',
              ),
            } as Record<NotificationOverviewCardKey, string>
          )[activeOverviewCardKey] || ''
        : null,
    [activeOverviewCardKey, t],
  );

  const resolveSourceTypeLabel = (value: string) =>
    t(
      `module.operationsCreditNotifications.sourceType.${value}`,
      value || EMPTY_LABEL,
    );

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
      <CreditNotificationOverviewCards
        overview={overview}
        applyOverviewFilter={applyOverviewFilter}
      />

      <CreditNotificationRecordsFilter
        draftFilters={draftFilters}
        updateDraftFilter={updateDraftFilter}
        searchRecords={searchRecords}
        resetRecords={resetRecords}
        activeOverviewCardKey={activeOverviewCardKey}
        activeOverviewLabel={activeOverviewItem || ''}
        clearOverviewFilter={clearOverviewFilter}
        resolveDeliveryStatusLabel={resolveDeliveryStatusLabel}
        resolveSkipReasonLabel={resolveSkipReasonLabel}
        resolveTypeLabel={resolveTypeLabel}
        resolveSourceTypeLabel={resolveSourceTypeLabel}
      />

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
