import React from 'react';
import { render, screen } from '@testing-library/react';
import AdminOverflowTooltipText from './AdminOverflowTooltipText';

jest.mock('@/components/ui/tooltip', () => ({
  __esModule: true,
  TooltipProvider: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  Tooltip: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => (
    <div data-testid='tooltip-content'>{children}</div>
  ),
}));

describe('AdminOverflowTooltipText', () => {
  test('renders text and tooltip content', () => {
    render(<AdminOverflowTooltipText text='Long content value' />);

    expect(screen.getAllByText('Long content value')).toHaveLength(2);
    expect(screen.getByTestId('tooltip-content')).toHaveTextContent(
      'Long content value',
    );
  });

  test('falls back to the provided empty value', () => {
    render(
      <AdminOverflowTooltipText
        text='   '
        emptyValue='-'
      />,
    );

    expect(screen.getAllByText('-')).toHaveLength(2);
  });
});
