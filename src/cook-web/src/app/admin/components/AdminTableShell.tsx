'use client';

import type { CSSProperties, ReactNode } from 'react';
import Loading from '@/components/loading';
import { TableCell, TableEmpty, TableRow } from '@/components/ui/Table';
import { TooltipProvider } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { AdminPagination, type AdminPaginationProps } from './AdminPagination';
import {
  ADMIN_TABLE_DESCENDANT_CLASS,
  ADMIN_TABLE_SHELL_CLASS,
} from './adminTableStyles';

type AdminTableRenderer = (emptyRow: ReactNode | null) => ReactNode;

type AdminStickyActionEmptyConfig = {
  contentColSpan: number;
  actionClassName?: string;
  actionStyle?: CSSProperties;
  contentClassName?: string;
  rowClassName?: string;
};

type AdminTableShellProps = {
  loading: boolean;
  isEmpty: boolean;
  emptyContent?: ReactNode;
  emptyColSpan?: number;
  stickyActionEmpty?: AdminStickyActionEmptyConfig;
  table: ReactNode | AdminTableRenderer;
  header?: ReactNode;
  footnote?: ReactNode;
  footer?: ReactNode;
  pagination?: AdminPaginationProps;
  withTooltipProvider?: boolean;
  containerClassName?: string;
  tableWrapperClassName?: string;
  tableWrapperStyle?: CSSProperties;
  tableWrapperTestId?: string;
  headerClassName?: string;
  loadingClassName?: string;
  footnoteClassName?: string;
  footerClassName?: string;
  footerTestId?: string;
  showFooterWhenLoading?: boolean;
};

const ADMIN_TABLE_FOOTNOTE_CLASS =
  'text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]';
const ADMIN_TABLE_HEADER_CLASS =
  'shrink-0 border-b border-[var(--base-border,#E5E5E5)] p-[var(--spacing-4,16px)]';

const renderTableContent = (
  table: ReactNode | AdminTableRenderer,
  emptyRow: ReactNode | null,
) => {
  if (typeof table === 'function') {
    return (table as AdminTableRenderer)(emptyRow);
  }
  return table;
};

const renderEmptyRow = ({
  emptyContent,
  emptyColSpan,
  stickyActionEmpty,
}: {
  emptyContent?: ReactNode;
  emptyColSpan?: number;
  stickyActionEmpty?: AdminStickyActionEmptyConfig;
}) => {
  if (!emptyContent) {
    return null;
  }

  if (stickyActionEmpty) {
    return (
      <TableRow
        className={cn('hover:bg-transparent', stickyActionEmpty.rowClassName)}
      >
        <TableCell
          colSpan={stickyActionEmpty.contentColSpan}
          className={cn(
            'px-4 py-10 text-center text-sm text-muted-foreground',
            stickyActionEmpty.contentClassName,
          )}
        >
          {emptyContent}
        </TableCell>
        <TableCell
          className={stickyActionEmpty.actionClassName}
          style={stickyActionEmpty.actionStyle}
        />
      </TableRow>
    );
  }

  if (!emptyColSpan) {
    return null;
  }

  return <TableEmpty colSpan={emptyColSpan}>{emptyContent}</TableEmpty>;
};

const shouldRenderPagination = (pagination?: AdminPaginationProps) => {
  if (!pagination) {
    return false;
  }

  const safePageCount = Number.isFinite(pagination.pageCount)
    ? pagination.pageCount
    : 1;
  const normalizedPageCount = Math.max(safePageCount, 1);

  return !pagination.hideWhenSinglePage || normalizedPageCount > 1;
};

export default function AdminTableShell({
  loading,
  isEmpty,
  emptyContent,
  emptyColSpan,
  stickyActionEmpty,
  table,
  header,
  footnote,
  footer,
  pagination,
  withTooltipProvider = false,
  containerClassName,
  tableWrapperClassName,
  tableWrapperTestId,
  headerClassName,
  loadingClassName,
  footnoteClassName,
  footerClassName,
  footerTestId,
  showFooterWhenLoading = false,
  tableWrapperStyle,
}: AdminTableShellProps) {
  const emptyRow = isEmpty
    ? renderEmptyRow({ emptyContent, emptyColSpan, stickyActionEmpty })
    : null;

  const tableContent = renderTableContent(table, emptyRow);
  const wrappedTableContent = withTooltipProvider ? (
    <TooltipProvider delayDuration={150}>{tableContent}</TooltipProvider>
  ) : (
    tableContent
  );
  const hasVisiblePagination = shouldRenderPagination(pagination);
  const shouldRenderFooter =
    (showFooterWhenLoading || !loading) &&
    Boolean(footnote || footer || hasVisiblePagination);

  return (
    <div className={cn('flex min-h-0 flex-col', containerClassName)}>
      <div
        data-testid={tableWrapperTestId}
        className={cn(
          ADMIN_TABLE_SHELL_CLASS,
          ADMIN_TABLE_DESCENDANT_CLASS,
          tableWrapperClassName,
        )}
        style={tableWrapperStyle}
      >
        {header ? (
          <div className={cn(ADMIN_TABLE_HEADER_CLASS, headerClassName)}>
            {header}
          </div>
        ) : null}
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
      {shouldRenderFooter ? (
        <div
          data-testid={footerTestId}
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
          {hasVisiblePagination && pagination ? (
            <AdminPagination
              {...pagination}
              className={cn('mx-0 w-auto justify-end', pagination.className)}
            />
          ) : (
            footer
          )}
        </div>
      ) : null}
    </div>
  );
}
