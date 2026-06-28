'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import type { DashboardEntryCourseItem } from '@/types/dashboard';
import { TableCell, TableRow } from '@/components/ui/Table';
import { getAdminStickyRightCellClass } from '@/app/admin/components/adminTableStyles';
import { buildAdminDashboardCourseDetailUrl } from './admin-dashboard-routes';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';

const DASHBOARD_TABLE_CELL_CLASS =
  'overflow-hidden whitespace-nowrap text-ellipsis';

export const formatLastActive = (value: string): string => {
  return formatAdminUtcDateTime(value) || '-';
};

export const formatOrderAmount = (
  value: string,
  currencySymbol: string,
): string => {
  const normalized = (value || '').trim();
  const matched = normalized.match(/^(-?\d+)(?:\.(\d+))?$/);
  if (!matched) {
    return `${currencySymbol}0.00`;
  }
  const integerPart = matched[1].replace(/^(-?)0+(?=\d)/, '$1');
  const decimalPart = (matched[2] || '').padEnd(2, '0').slice(0, 2);
  return `${currencySymbol}${integerPart}.${decimalPart}`;
};

type DashboardCourseTableRowProps = {
  item: DashboardEntryCourseItem;
  currencySymbol: string;
  viewCourseLabel: string;
  viewOrdersLabel: string;
  onCourseDetailClick: (shifuBid: string) => void;
  onOrderClick: (shifuBid: string) => void;
};

export function DashboardCourseTableRow({
  item,
  currencySymbol,
  viewCourseLabel,
  viewOrdersLabel,
  onCourseDetailClick,
  onOrderClick,
}: DashboardCourseTableRowProps) {
  const detailUrl = buildAdminDashboardCourseDetailUrl(item.shifu_bid);
  const canOpenDetail = Boolean(detailUrl);
  const courseLabel = item.shifu_name || item.shifu_bid;

  return (
    <TableRow>
      <TableCell className={cn(DASHBOARD_TABLE_CELL_CLASS, 'min-w-[280px]')}>
        <div className='max-w-[320px] truncate text-sm text-foreground'>
          {courseLabel}
        </div>
      </TableCell>
      <TableCell
        className={cn(
          DASHBOARD_TABLE_CELL_CLASS,
          'min-w-[120px] text-sm text-foreground',
        )}
      >
        {item.learner_count}
      </TableCell>
      <TableCell className={cn(DASHBOARD_TABLE_CELL_CLASS, 'min-w-[120px]')}>
        <span className='text-sm text-foreground'>{item.order_count}</span>
      </TableCell>
      <TableCell
        className={cn(
          DASHBOARD_TABLE_CELL_CLASS,
          'min-w-[140px] text-sm text-foreground',
        )}
      >
        {formatOrderAmount(item.order_amount, currencySymbol)}
      </TableCell>
      <TableCell
        className={cn(
          DASHBOARD_TABLE_CELL_CLASS,
          'min-w-[180px] text-sm text-foreground',
        )}
      >
        {formatLastActive(item.last_active_at)}
      </TableCell>
      <TableCell
        className={getAdminStickyRightCellClass(
          cn(
            DASHBOARD_TABLE_CELL_CLASS,
            'min-w-[160px] text-sm text-foreground',
          ),
        )}
      >
        <div className='flex items-center gap-3'>
          <button
            type='button'
            onClick={() => onCourseDetailClick(item.shifu_bid)}
            disabled={!canOpenDetail}
            className='p-0 text-sm font-medium text-primary transition hover:underline disabled:cursor-not-allowed disabled:text-muted-foreground disabled:no-underline'
          >
            {viewCourseLabel}
          </button>
          <button
            type='button'
            onClick={() => onOrderClick(item.shifu_bid)}
            disabled={!item.shifu_bid.trim()}
            className='p-0 text-sm font-medium text-primary transition hover:underline disabled:cursor-not-allowed disabled:text-muted-foreground disabled:no-underline'
          >
            {viewOrdersLabel}
          </button>
        </div>
      </TableCell>
    </TableRow>
  );
}
