import type { ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import {
  createDateRangeFilterItem,
  createSelectFilterItem,
  createTextFilterItem,
} from './adminFilterFieldBuilders';

jest.mock('@/components/ui/Select', () => ({
  Select: ({ children }: { children: ReactNode }) => (
    <div data-testid='select-root'>{children}</div>
  ),
  SelectTrigger: ({
    children,
    className,
  }: {
    children: ReactNode;
    className?: string;
  }) => (
    <button
      data-testid='select-trigger'
      className={className}
    >
      {children}
    </button>
  ),
  SelectValue: ({ placeholder }: { placeholder?: string }) => (
    <span>{placeholder}</span>
  ),
  SelectContent: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  SelectItem: ({ children, value }: { children: ReactNode; value: string }) => (
    <div data-value={value}>{children}</div>
  ),
}));

describe('adminFilterFieldBuilders', () => {
  test('builds text filter item with clearable input', () => {
    const onChange = jest.fn();
    const onSubmit = jest.fn();
    const item = createTextFilterItem({
      key: 'keyword',
      label: 'Keyword',
      value: 'abc',
      placeholder: 'Search keyword',
      clearLabel: 'Clear',
      onChange,
      onSubmit,
    });

    render(item.component);
    const input = screen.getByPlaceholderText('Search keyword');
    expect(input).toHaveValue('abc');

    fireEvent.change(input, { target: { value: 'abcd' } });
    expect(onChange).toHaveBeenCalledWith('abcd');

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  test('builds select filter item with provided options', () => {
    const item = createSelectFilterItem({
      key: 'status',
      label: 'Status',
      value: '__all__',
      placeholder: 'Choose status',
      options: [
        { value: '__all__', label: 'All' },
        { value: 'active', label: 'Active' },
      ],
      onChange: jest.fn(),
    });

    render(item.component);
    expect(screen.getByText('Choose status')).toBeInTheDocument();
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  test('builds date range filter item with trigger placeholder', () => {
    const item = createDateRangeFilterItem({
      key: 'date_range',
      label: 'Date',
      startValue: '',
      endValue: '',
      placeholder: 'Start ~ End',
      resetLabel: 'Reset',
      clearLabel: 'Clear',
      onChange: jest.fn(),
    });

    render(item.component);
    expect(
      screen.getByRole('button', { name: 'Start ~ End' }),
    ).toBeInTheDocument();
  });
});
