'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import type { DashboardEntryCourseItem } from '@/types/dashboard';
import { TableCell, TableRow } from '@/components/ui/Table';
import { buildAdminDashboardCourseDetailUrl } from './admin-dashboard-routes';

const DASHBOARD_TABLE_CELL_CLASS =
  'whitespace-nowrap overflow-hidden text-ellipsis border-r border-border last:border-r-0';

export const formatLastActive = (
  value: string,
  displayValue?: string,
): string => {
  if (displayValue) {
    return displayValue;
  }
  if (!value) {
    return '-';
  }
  return value;
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
  const courseLabel = item.shifu_name || item.shifu_bid;

  return (
    <TableRow>
      <TableCell className={cn(DASHBOARD_TABLE_CELL_CLASS, 'min-w-[280px]')}>
        {canOpenDetail ? (
          <button
            type='button'
            onClick={() => onCourseDetailClick(item.shifu_bid)}
            className={cn(
              'group max-w-[320px] text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            )}
            aria-label={`${courseLabel}-${item.shifu_bid}`}
          >
            <div className='truncate text-sm text-primary group-hover:underline'>
              {courseLabel}
            </div>
            <div className='mt-1 truncate text-xs text-muted-foreground transition group-hover:text-primary/80'>
              {item.shifu_bid}
            </div>
          </button>
        ) : (
          <>
            <div className='max-w-[320px] truncate text-sm text-foreground'>
              {courseLabel}
            </div>
            <div className='mt-1 max-w-[320px] truncate text-xs text-muted-foreground'>
              {item.shifu_bid}
            </div>
          </>
        )}
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
        {formatLastActive(item.last_active_at, item.last_active_at_display)}
      </TableCell>
    </TableRow>
  );
}
