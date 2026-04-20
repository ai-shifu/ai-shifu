'use client';

import type { ReactNode } from 'react';
import Loading from '@/components/loading';
import { TableEmpty } from '@/components/ui/Table';
import { TooltipProvider } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type AdminTableRenderer = (emptyRow: ReactNode | null) => ReactNode;

type AdminTableShellProps = {
  loading: boolean;
  isEmpty: boolean;
  emptyContent?: ReactNode;
  emptyColSpan?: number;
  table: ReactNode | AdminTableRenderer;
  footer?: ReactNode;
  withTooltipProvider?: boolean;
  containerClassName?: string;
  tableWrapperClassName?: string;
  loadingClassName?: string;
  footerClassName?: string;
};

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
  footer,
  withTooltipProvider = false,
  containerClassName,
  tableWrapperClassName,
  loadingClassName,
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
          'rounded-xl border border-border bg-white shadow-sm',
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
      {loading || !footer ? null : (
        <div className={cn('mt-4 flex justify-end', footerClassName)}>
          {footer}
        </div>
      )}
    </div>
  );
}
