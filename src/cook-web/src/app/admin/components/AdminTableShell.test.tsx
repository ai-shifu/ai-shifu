import React from 'react';
import { render, screen } from '@testing-library/react';
import AdminTableShell from './AdminTableShell';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';

const MOCK_LOADING_LABEL = 'Loading';
const NAME_LABEL = 'Name';
const STATUS_LABEL = 'Status';

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div>{MOCK_LOADING_LABEL}</div>,
}));

describe('AdminTableShell', () => {
  test('passes the default empty row to table renderers', () => {
    render(
      <AdminTableShell
        loading={false}
        isEmpty
        emptyContent='No records'
        emptyColSpan={2}
        table={emptyRow => (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{NAME_LABEL}</TableHead>
                <TableHead>{STATUS_LABEL}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>{emptyRow}</TableBody>
          </Table>
        )}
      />,
    );

    expect(screen.getByText('No records')).toBeInTheDocument();
    expect(screen.getByText('No records').closest('td')).toHaveAttribute(
      'colspan',
      '2',
    );
  });

  test('renders sticky action empty rows with a separate action cell', () => {
    render(
      <AdminTableShell
        loading={false}
        isEmpty
        emptyContent='No campaigns'
        stickyActionEmpty={{
          contentColSpan: 3,
          actionClassName: 'sticky-action-cell',
        }}
        table={emptyRow => (
          <Table>
            <TableBody>{emptyRow}</TableBody>
          </Table>
        )}
      />,
    );

    const contentCell = screen.getByText('No campaigns').closest('td');

    expect(contentCell).toHaveAttribute('colspan', '3');
    expect(document.querySelector('.sticky-action-cell')).toBeInTheDocument();
  });
});
