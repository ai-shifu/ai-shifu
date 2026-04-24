import React from 'react';
import { render, screen } from '@testing-library/react';
import AdminDateRangeFilter from './AdminDateRangeFilter';

jest.mock('@/components/ui/Button', () => ({
  __esModule: true,
  Button: ({
    children,
    ...props
  }: React.PropsWithChildren<
    React.ButtonHTMLAttributes<HTMLButtonElement>
  >) => <button {...props}>{children}</button>,
}));

jest.mock('@/components/ui/Popover', () => ({
  __esModule: true,
  Popover: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  PopoverTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  PopoverContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/ui/Calendar', () => ({
  __esModule: true,
  Calendar: () => <div>calendar</div>,
}));

describe('AdminDateRangeFilter', () => {
  test('does not duplicate the aria-label when only the end date is present', () => {
    render(
      <AdminDateRangeFilter
        startValue=''
        endValue='2026-04-06'
        placeholder='Select date'
        resetLabel='Reset'
        clearLabel='Clear'
        triggerAriaLabel='Select date'
        onChange={() => undefined}
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Select date' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Select date Select date' }),
    ).not.toBeInTheDocument();
  });
});
