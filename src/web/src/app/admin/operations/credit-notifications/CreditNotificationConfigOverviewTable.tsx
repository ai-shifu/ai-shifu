import type { ReactNode } from 'react';
import {
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { cn } from '@/lib/utils';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';

export type CreditNotificationConfigOverviewColumn = {
  key: string;
  header: ReactNode;
  className?: string;
  stickyRight?: boolean;
};

type CreditNotificationConfigOverviewTableProps<Row extends { key: string }> = {
  columns: CreditNotificationConfigOverviewColumn[];
  rows: Row[];
  renderCell: (
    row: Row,
    column: CreditNotificationConfigOverviewColumn,
  ) => ReactNode;
};

const CELL_CLASS_NAME = 'px-3 py-3 align-middle';

export function CreditNotificationConfigOverviewTable<
  Row extends { key: string },
>({
  columns,
  rows,
  renderCell,
}: CreditNotificationConfigOverviewTableProps<Row>) {
  return (
    <div className='overflow-hidden rounded-lg border border-border bg-white'>
      <Table containerClassName='max-h-none overflow-auto'>
        <TableHeader>
          <TableRow>
            {columns.map(column => (
              <TableHead
                key={column.key}
                className={
                  column.stickyRight
                    ? getAdminStickyRightHeaderClass(column.className)
                    : cn('px-3', column.className)
                }
              >
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map(row => (
            <TableRow key={row.key}>
              {columns.map(column => (
                <TableCell
                  key={column.key}
                  className={
                    column.stickyRight
                      ? getAdminStickyRightCellClass(column.className)
                      : cn(CELL_CLASS_NAME, column.className)
                  }
                >
                  {renderCell(row, column)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
