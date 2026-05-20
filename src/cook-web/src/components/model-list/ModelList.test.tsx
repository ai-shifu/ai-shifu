import React from 'react';
import { render, screen, within } from '@testing-library/react';

import ModelList from './ModelList';

const mockShifuState = {
  models: [
    {
      value: 'qwen/deepseek-v4-flash',
      label: 'DeepSeek-V4-Flash',
      creditMultiplier: 1,
    },
    {
      value: 'ark/doubao-seed-2-0-lite-260428',
      label: 'Doubao-Seed-2.0-lite',
      creditMultiplier: 3,
    },
    {
      value: 'qwen/no-rate-model',
      label: 'No Rate',
      creditMultiplier: null,
    },
  ],
};

jest.mock('@/store', () => ({
  __esModule: true,
  useShifu: () => mockShifuState,
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('../ui/Select', () => ({
  __esModule: true,
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({
    children,
    className,
  }: React.PropsWithChildren<{ className?: string }>) => (
    <button data-class={className}>{children}</button>
  ),
  SelectValue: ({
    children,
    placeholder,
  }: React.PropsWithChildren<{ placeholder?: string }>) => (
    <span>{children ?? placeholder}</span>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => (
    <div role='listbox'>{children}</div>
  ),
  SelectItem: ({
    children,
    value,
    indicatorClassName,
    className,
  }: React.PropsWithChildren<{
    value: string;
    textValue?: string;
    indicatorClassName?: string;
    className?: string;
  }>) => (
    <div
      role='option'
      data-value={value}
      data-indicator-class={indicatorClassName}
      data-class={className}
    >
      {children}
    </div>
  ),
}));

describe('ModelList', () => {
  test('renders multiplier badges only for models that have a multiplier', () => {
    render(
      <ModelList
        value=''
        onChange={() => undefined}
      />,
    );

    expect(screen.getAllByText('common.core.default')).toHaveLength(2);
    expect(screen.getByText('DeepSeek-V4-Flash')).toBeInTheDocument();
    expect(screen.getByText('Doubao-Seed-2.0-lite')).toBeInTheDocument();
    expect(screen.getByText('No Rate')).toBeInTheDocument();
    expect(screen.getAllByText('1x')).toHaveLength(3);
    expect(screen.getByText('3x')).toBeInTheDocument();

    const trigger = screen.getByRole('button');
    expect(trigger).toHaveAttribute(
      'data-class',
      expect.stringContaining('pl-3'),
    );
    expect(
      within(trigger).getByText('common.core.default'),
    ).toBeInTheDocument();
    expect(within(trigger).getByText('1x')).toBeInTheDocument();

    const noRateOption = screen.getByText('No Rate').closest('[role="option"]');
    expect(noRateOption).toBeTruthy();
    expect(within(noRateOption as HTMLElement).queryByText(/x$/)).toBeNull();

    const defaultOption = screen
      .getByRole('listbox')
      .querySelector('[data-value="__empty__"]');
    expect(defaultOption).toBeTruthy();
    expect(defaultOption).toHaveAttribute(
      'data-class',
      expect.stringContaining('pl-3'),
    );
    expect(defaultOption).toHaveAttribute(
      'data-indicator-class',
      expect.stringContaining('right-3'),
    );
    expect(
      within(defaultOption as HTMLElement).getByText('1x'),
    ).toBeInTheDocument();
  });
});
