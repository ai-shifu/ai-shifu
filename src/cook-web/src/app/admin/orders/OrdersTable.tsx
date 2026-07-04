'use client';

import type { CSSProperties, MouseEvent as ReactMouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CLASS,
  ADMIN_TABLE_HEADER_LAST_CELL_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type { OrderSummary } from '@/components/order/order-types';
import { Button } from '@/components/ui/Button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import { DEFAULT_COLUMN_WIDTHS, type ColumnKey } from './ordersPageShared';

type OrdersTableProps = {
  orders: OrderSummary[];
  loading: boolean;
  total: number;
  pageIndex: number;
  pageCount: number;
  isEmailMode: boolean;
  defaultUserName: string;
  getColumnStyle: (key: ColumnKey) => CSSProperties;
  getResizeHandleProps: (key: ColumnKey) => {
    onMouseDown: (event: ReactMouseEvent<HTMLElement>) => void;
    'aria-hidden': true | 'true';
  };
  formatMoney: (value?: string) => string;
  resolveStatusLabel: (order: OrderSummary) => string;
  onPageChange: (nextPage: number) => void;
  onViewDetail: (order: OrderSummary) => void;
};

export default function OrdersTable({
  orders,
  loading,
  total,
  pageIndex,
  pageCount,
  isEmailMode,
  defaultUserName,
  getColumnStyle,
  getResizeHandleProps,
  formatMoney,
  resolveStatusLabel,
  onPageChange,
  onViewDetail,
}: OrdersTableProps) {
  const { t } = useTranslation();

  const renderResizeHandle = (key: ColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getResizeHandleProps(key)}
    />
  );

  const renderTooltipText = (text?: string, className?: string) => {
    return (
      <AdminTooltipText
        text={text}
        emptyValue='-'
        forceTooltip
        className={cn('block w-full min-w-0 truncate', className)}
      />
    );
  };

  const renderPlainTableText = (text?: string, className?: string) => {
    const value = text?.trim() || '-';
    return (
      <span className={cn('block w-full min-w-0 truncate', className)}>
        {value}
      </span>
    );
  };

  return (
    <AdminTableShell
      loading={loading}
      isEmpty={orders.length === 0}
      emptyContent={t('module.order.emptyList')}
      emptyColSpan={Object.keys(DEFAULT_COLUMN_WIDTHS).length}
      withTooltipProvider
      tableWrapperClassName='max-h-[calc(100vh-20rem)] overflow-auto'
      footnote={t('module.order.totalCount', { count: total })}
      pagination={{
        pageIndex,
        pageCount,
        onPageChange,
        prevLabel: t('module.order.paginationPrev'),
        nextLabel: t('module.order.paginationNext'),
        prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
        nextAriaLabel: t('module.order.paginationNextAriaLabel'),
      }}
      table={emptyRow => (
        <Table className='table-auto'>
          <TableHeader>
            <TableRow>
              <TableHead
                className={cn(
                  ADMIN_TABLE_HEADER_CELL_CLASS,
                  'h-10 whitespace-nowrap text-center text-xs',
                )}
                style={getColumnStyle('shifu')}
              >
                {t('module.order.table.shifu')}
                {renderResizeHandle('shifu')}
              </TableHead>
              <TableHead
                className={cn(
                  ADMIN_TABLE_HEADER_CELL_CLASS,
                  'h-10 whitespace-nowrap text-left text-xs',
                )}
                style={getColumnStyle('user')}
              >
                {t('module.order.table.user')}
                {renderResizeHandle('user')}
              </TableHead>
              <TableHead
                className={cn(
                  ADMIN_TABLE_HEADER_CELL_CLASS,
                  'h-10 whitespace-nowrap text-center text-xs',
                )}
                style={getColumnStyle('status')}
              >
                {t('module.order.table.status')}
                {renderResizeHandle('status')}
              </TableHead>
              <TableHead
                className={cn(
                  ADMIN_TABLE_HEADER_CELL_CLASS,
                  'h-10 whitespace-nowrap text-center text-xs',
                )}
                style={getColumnStyle('paidAmount')}
              >
                {t('module.order.fields.paid')}
                {renderResizeHandle('paidAmount')}
              </TableHead>
              <TableHead
                className={cn(
                  ADMIN_TABLE_HEADER_CELL_CLASS,
                  'h-10 whitespace-nowrap text-center text-xs',
                )}
                style={getColumnStyle('discountInfo')}
              >
                {t('module.order.fields.discount')}
                {renderResizeHandle('discountInfo')}
              </TableHead>
              <TableHead
                className={cn(
                  ADMIN_TABLE_HEADER_CELL_CLASS,
                  'h-10 whitespace-nowrap text-center text-xs',
                )}
                style={getColumnStyle('payment')}
              >
                {t('module.order.table.payment')}
                {renderResizeHandle('payment')}
              </TableHead>
              <TableHead
                className={cn(
                  ADMIN_TABLE_HEADER_CELL_CLASS,
                  'h-10 whitespace-nowrap text-center text-xs',
                )}
                style={getColumnStyle('createdAt')}
              >
                {t('module.order.table.createdAt')}
                {renderResizeHandle('createdAt')}
              </TableHead>
              <TableHead
                className={cn(
                  ADMIN_TABLE_HEADER_LAST_CELL_CLASS,
                  'h-10 whitespace-nowrap text-center text-xs',
                )}
                style={getColumnStyle('orderId')}
              >
                {t('module.order.table.orderId')}
                {renderResizeHandle('orderId')}
              </TableHead>
              <TableHead
                className={getAdminStickyRightHeaderClass(
                  'h-10 whitespace-nowrap text-center text-xs',
                )}
                style={getColumnStyle('action')}
              >
                {t('module.order.table.action')}
                {renderResizeHandle('action')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {emptyRow}
            {orders.map(order => {
              const userContact =
                (isEmailMode ? order.user_email : order.user_mobile) ||
                order.user_bid ||
                '-';
              const userName = order.user_nickname || defaultUserName;

              return (
                <TableRow key={order.order_bid}>
                  <TableCell
                    className='overflow-hidden text-ellipsis whitespace-nowrap border-r border-border px-3 py-2 text-center'
                    style={getColumnStyle('shifu')}
                  >
                    {renderTooltipText(
                      order.shifu_name || order.shifu_bid,
                      'text-foreground',
                    )}
                  </TableCell>
                  <TableCell
                    className='border-r border-border px-3 py-2 align-middle'
                    style={getColumnStyle('user')}
                  >
                    <div className='space-y-1'>
                      {renderTooltipText(
                        userContact,
                        'text-sm font-medium text-foreground',
                      )}
                      {renderTooltipText(
                        userName,
                        'block text-xs text-muted-foreground',
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className='overflow-hidden text-ellipsis whitespace-nowrap border-r border-border px-3 py-2 text-center'
                    style={getColumnStyle('status')}
                  >
                    {renderPlainTableText(resolveStatusLabel(order))}
                  </TableCell>
                  <TableCell
                    className='border-r border-border px-3 py-2 align-middle'
                    style={getColumnStyle('paidAmount')}
                  >
                    <div className='text-center'>
                      {renderPlainTableText(
                        formatMoney(order.paid_price),
                        'text-foreground',
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className='border-r border-border px-3 py-2 align-middle'
                    style={getColumnStyle('discountInfo')}
                  >
                    <div className='text-center'>
                      {renderPlainTableText(
                        order.discount_amount && order.discount_amount !== '0'
                          ? formatMoney(order.discount_amount)
                          : '-',
                        'text-foreground',
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className='overflow-hidden text-ellipsis whitespace-nowrap border-r border-border px-3 py-2 text-center'
                    style={getColumnStyle('payment')}
                  >
                    <div className='text-sm text-foreground'>
                      {renderPlainTableText(
                        t(order.payment_channel_key),
                        'text-sm',
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className='overflow-hidden text-ellipsis whitespace-nowrap px-3 py-2 text-center'
                    style={getColumnStyle('createdAt')}
                  >
                    {renderPlainTableText(
                      formatAdminUtcDateTime(order.created_at),
                    )}
                  </TableCell>
                  <TableCell
                    className='overflow-hidden text-ellipsis whitespace-nowrap px-3 py-2 text-center'
                    style={getColumnStyle('orderId')}
                  >
                    {renderTooltipText(order.order_bid)}
                  </TableCell>
                  <TableCell
                    className={getAdminStickyRightCellClass(
                      'whitespace-nowrap px-3 py-2 text-center',
                    )}
                    style={getColumnStyle('action')}
                  >
                    <Button
                      size='sm'
                      variant='ghost'
                      className='h-auto justify-start rounded-none p-0 text-primary hover:bg-transparent hover:text-primary'
                      onClick={() => onViewDetail(order)}
                    >
                      {t('module.order.table.view')}
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    />
  );
}
