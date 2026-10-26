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
    id,
    'aria-labelledby': ariaLabelledBy,
  }: {
    children: ReactNode;
    className?: string;
    id?: string;
    'aria-labelledby'?: string;
  }) => (
    <button
      data-testid='select-trigger'
      className={className}
      id={id}
      aria-labelledby={ariaLabelledBy}
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
  SelectItem: ({
    children,
    value,
    className,
  }: {
    children: ReactNode;
    value: string;
    className?: string;
  }) => (
    <div
      data-value={value}
      className={className}
    >
      {children}
    </div>
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
      labelId: 'status-label',
      value: '__all__',
      placeholder: 'Choose status',
      options: [
        { value: '__all__', label: 'All' },
        { value: 'active', label: 'Active' },
      ],
      onChange: jest.fn(),
      triggerId: 'status-trigger',
      triggerAriaLabelledBy: 'status-label',
    });

    render(item.component);
    expect(screen.getByText('Choose status')).toBeInTheDocument();
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByTestId('select-trigger')).toHaveAttribute(
      'id',
      'status-trigger',
    );
    expect(screen.getByTestId('select-trigger')).toHaveAttribute(
      'aria-labelledby',
      'status-label',
    );
    expect(screen.getByTestId('select-trigger')).toHaveClass('h-9');
  });

  test('applies admin select item classes before custom item classes', () => {
    const item = createSelectFilterItem({
      key: 'status',
      label: 'Status',
      value: '__all__',
      placeholder: 'Choose status',
      options: [{ value: '__all__', label: 'All' }],
      onChange: jest.fn(),
      selectItemClassName: 'min-w-[140px]',
    });

    render(item.component);

    const optionElement = screen.getByText('All');
    expect(optionElement).toHaveClass('data-[state=checked]:bg-muted');
    expect(optionElement).toHaveClass('data-[state=checked]:text-foreground');
    expect(optionElement).toHaveClass('min-w-[140px]');
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

  test('passes trigger aria label to date range filter', () => {
    const item = createDateRangeFilterItem({
      key: 'date_range',
      label: 'Date',
      startValue: '',
      endValue: '',
      triggerAriaLabel: 'Filter by date range',
      placeholder: 'Start ~ End',
      resetLabel: 'Reset',
      clearLabel: 'Clear',
      onChange: jest.fn(),
    });

    render(item.component);
    expect(
      screen.getByRole('button', { name: 'Filter by date range' }),
    ).toBeInTheDocument();
  });
});
