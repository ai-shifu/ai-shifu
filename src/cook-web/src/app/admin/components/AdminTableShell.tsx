'use client';

import type { ReactNode } from 'react';
import Loading from '@/components/loading';
import { TableEmpty } from '@/components/ui/Table';
import { TooltipProvider } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import {
  AdminPagination,
  type AdminPaginationProps,
} from './AdminPagination';
import {
  ADMIN_TABLE_DESCENDANT_CLASS,
  ADMIN_TABLE_SHELL_CLASS,
} from './adminTableStyles';

type AdminTableRenderer = (emptyRow: ReactNode | null) => ReactNode;

type AdminTableShellProps = {
  loading: boolean;
  isEmpty: boolean;
  emptyContent?: ReactNode;
  emptyColSpan?: number;
  table: ReactNode | AdminTableRenderer;
  footnote?: ReactNode;
  footer?: ReactNode;
  pagination?: AdminPaginationProps;
  withTooltipProvider?: boolean;
  containerClassName?: string;
  tableWrapperClassName?: string;
  loadingClassName?: string;
  footnoteClassName?: string;
  footerClassName?: string;
};

const ADMIN_TABLE_FOOTNOTE_CLASS =
  'text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]';

const renderTableContent = (
  table: ReactNode | AdminTableRenderer,
  emptyRow: ReactNode | null,
) => {
  if (typeof table === 'function') {
    return (table as AdminTableRenderer)(emptyRow);
  }
  return table;
};

export default function AdminTableShell({
  loading,
  isEmpty,
  emptyContent,
  emptyColSpan,
  table,
  footnote,
  footer,
  pagination,
  withTooltipProvider = false,
  containerClassName,
  tableWrapperClassName,
  loadingClassName,
  footnoteClassName,
  footerClassName,
}: AdminTableShellProps) {
  const emptyRow =
    isEmpty && emptyContent && emptyColSpan ? (
      <TableEmpty colSpan={emptyColSpan}>{emptyContent}</TableEmpty>
    ) : null;

  const tableContent = renderTableContent(table, emptyRow);
  const wrappedTableContent = withTooltipProvider ? (
    <TooltipProvider delayDuration={150}>{tableContent}</TooltipProvider>
  ) : (
    tableContent
  );

  return (
    <div className={cn('flex min-h-0 flex-col', containerClassName)}>
      <div
        className={cn(
          ADMIN_TABLE_SHELL_CLASS,
          ADMIN_TABLE_DESCENDANT_CLASS,
          tableWrapperClassName,
        )}
      >
        {loading ? (
          <div
            className={cn(
              'flex h-40 items-center justify-center',
              loadingClassName,
            )}
          >
            <Loading />
          </div>
        ) : (
          wrappedTableContent
        )}
      </div>
      {loading || (!footnote && !footer && !pagination) ? null : (
        <div
          className={cn(
            'mt-4 flex items-center justify-between gap-4',
            footerClassName,
          )}
        >
          {footnote ? (
            <div className={cn(ADMIN_TABLE_FOOTNOTE_CLASS, footnoteClassName)}>
              {footnote}
            </div>
          ) : (
            <div />
          )}
          {pagination ? (
            <AdminPagination
              {...pagination}
              className={cn('mx-0 w-auto justify-end', pagination.className)}
            />
          ) : (
            footer
          )}
        </div>
      )}
    </div>
  );
}
