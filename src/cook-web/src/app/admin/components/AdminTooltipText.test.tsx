import React from 'react';
import { render, screen } from '@testing-library/react';
import AdminTooltipText from './AdminTooltipText';

jest.mock('@/components/ui/tooltip', () => ({
  __esModule: true,
  Tooltip: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => (
    <div data-testid='tooltip-content'>{children}</div>
  ),
}));

describe('AdminTooltipText', () => {
  test('renders text and tooltip content', () => {
    render(<AdminTooltipText text='Long content value' />);

    expect(screen.getAllByText('Long content value')).toHaveLength(2);
    expect(screen.getByTestId('tooltip-content')).toHaveTextContent(
      'Long content value',
    );
  });

  test('falls back to the provided empty value', () => {
    render(
      <AdminTooltipText
        text='   '
        emptyValue='-'
      />,
    );

    expect(screen.getAllByText('-')).toHaveLength(2);
  });

  test('trims surrounding whitespace before rendering', () => {
    render(<AdminTooltipText text='  Course One  ' />);

    expect(screen.getAllByText('Course One')).toHaveLength(2);
    expect(screen.queryByText('  Course One  ')).not.toBeInTheDocument();
  });
});
