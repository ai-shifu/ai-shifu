'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import type { DashboardEntryCourseItem } from '@/types/dashboard';
import { TableCell, TableRow } from '@/components/ui/Table';
import { buildAdminDashboardCourseDetailUrl } from './admin-dashboard-routes';

const DASHBOARD_TABLE_CELL_CLASS =
  'whitespace-nowrap overflow-hidden text-ellipsis border-r border-border last:border-r-0';

export const formatLastActive = (value: string): string => {
  if (!value) {
    return '-';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
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
  orderButtonLabel: string;
  onCourseDetailClick: (shifuBid: string) => void;
  onOrderClick: (shifuBid: string) => void;
};

export function DashboardCourseTableRow({
  item,
  currencySymbol,
  orderButtonLabel,
  onCourseDetailClick,
  onOrderClick,
}: DashboardCourseTableRowProps) {
  const detailUrl = buildAdminDashboardCourseDetailUrl(item.shifu_bid);
  const canOpenDetail = Boolean(detailUrl);

  const handleRowKeyDown = (
    event: React.KeyboardEvent<HTMLTableRowElement>,
  ) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    event.preventDefault();
    onCourseDetailClick(item.shifu_bid);
  };

  return (
    <TableRow
      className={cn(
        canOpenDetail && 'cursor-pointer hover:bg-muted/70 focus:bg-muted/70',
      )}
      onClick={() => onCourseDetailClick(item.shifu_bid)}
      onKeyDown={handleRowKeyDown}
      role={canOpenDetail ? 'link' : undefined}
      tabIndex={canOpenDetail ? 0 : undefined}
      aria-label={
        canOpenDetail
          ? `${item.shifu_name || item.shifu_bid}-${item.shifu_bid}`
          : undefined
      }
    >
      <TableCell className={cn(DASHBOARD_TABLE_CELL_CLASS, 'min-w-[280px]')}>
        <div className='max-w-[320px] truncate text-sm text-foreground'>
          {item.shifu_name || item.shifu_bid}
        </div>
        <div className='mt-1 max-w-[320px] truncate text-xs text-muted-foreground'>
          {item.shifu_bid}
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
        <button
          type='button'
          onClick={event => {
            event.stopPropagation();
            onOrderClick(item.shifu_bid);
          }}
          disabled={!item.shifu_bid.trim()}
          aria-label={orderButtonLabel}
          className={cn(
            'text-sm font-medium text-primary transition hover:underline disabled:cursor-not-allowed disabled:text-muted-foreground disabled:no-underline',
          )}
        >
          {item.order_count}
        </button>
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
    </TableRow>
  );
}
