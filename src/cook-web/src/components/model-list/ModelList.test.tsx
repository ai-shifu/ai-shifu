import type React from 'react';
import { render, screen } from '@testing-library/react';

import ModelList from './ModelList';

jest.mock('../ui/Select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SelectItem: ({
    children,
    value,
  }: {
    children: React.ReactNode;
    value: string;
  }) => (
    <div
      role='option'
      aria-selected={false}
      data-value={value}
    >
      {children}
    </div>
  ),
  SelectTrigger: ({ children }: { children: React.ReactNode }) => (
    <button type='button'>{children}</button>
  ),
  SelectValue: ({ placeholder }: { placeholder?: string }) => (
    <span>{placeholder}</span>
  ),
}));

jest.mock('../../store/useShifu', () => ({
  useShifu: () => ({ models: [] }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('ModelList', () => {
  test('renders custom options with credit multiplier labels', async () => {
    render(
      <ModelList
        value='minimax/speech-01-turbo'
        onChange={jest.fn()}
        showDefaultOption={false}
        options={[
          {
            value: 'minimax/speech-01-turbo',
            label: 'MiniMax Turbo',
            credit_multiplier_label: '2x',
          },
        ]}
      />,
    );

    expect(await screen.findByText('MiniMax Turbo')).toBeInTheDocument();
    expect(screen.getByText('2x')).toBeInTheDocument();
    expect(screen.queryByText('common.core.default')).not.toBeInTheDocument();
  });
});
