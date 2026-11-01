import React from 'react';
import { render, screen } from '@testing-library/react';
import CourseFeedbackSummaryCards from './CourseFeedbackSummaryCards';
import FollowUpSourceStatusBadge from './FollowUpSourceStatusBadge';
import StackedTooltipText from './StackedTooltipText';

jest.mock('@/app/admin/components/AdminTooltipText', () => ({
  __esModule: true,
  default: ({
    text,
    emptyValue,
    className,
  }: {
    text?: string;
    emptyValue: string;
    className?: string;
  }) => (
    <span
      data-testid='tooltip-text'
      className={className}
    >
      {text || emptyValue}
    </span>
  ),
}));

describe('CourseFeedbackSummaryCards', () => {
  const cards = [
    { key: 'count', label: 'Count', value: '12', tone: 'value' as const },
    {
      key: 'latest',
      label: 'Latest',
      value: '2026-10-01 08:30:00',
      tone: 'timestamp' as const,
    },
  ];

  test('renders values and splits timestamps with compact sizing', () => {
    const { container } = render(
      <CourseFeedbackSummaryCards
        cards={cards}
        gridClassName='summary-grid'
        size='compact'
      />,
    );

    expect(container.firstChild).toHaveClass('summary-grid');
    expect(screen.getByText('Count')).toBeInTheDocument();
    expect(screen.getByText('12')).toHaveClass('text-xl');
    expect(screen.getByText('2026-10-01')).toHaveClass('text-base');
    expect(screen.getByText('08:30:00')).toHaveClass('text-sm');
  });

  test('uses larger text with comfortable sizing', () => {
    render(
      <CourseFeedbackSummaryCards
        cards={cards}
        gridClassName='summary-grid'
        size='comfortable'
      />,
    );

    expect(screen.getByText('12')).toHaveClass('text-2xl');
    expect(screen.getByText('2026-10-01')).toHaveClass('text-lg');
    expect(screen.getByText('08:30:00')).toHaveClass('text-base');
  });
});

describe('FollowUpSourceStatusBadge', () => {
  test('switches label and tone by source status', () => {
    const { rerender } = render(
      <FollowUpSourceStatusBadge
        hasSourceOutput
        resolvedLabel='Resolved'
        missingLabel='Missing'
      />,
    );
    expect(screen.getByText('Resolved')).toHaveClass('text-emerald-700');

    rerender(
      <FollowUpSourceStatusBadge
        hasSourceOutput={false}
        resolvedLabel='Resolved'
        missingLabel='Missing'
      />,
    );
    expect(screen.getByText('Missing')).toHaveClass('text-amber-700');
  });
});

describe('StackedTooltipText', () => {
  test('omits the secondary line when it is empty', () => {
    render(
      <StackedTooltipText
        primary='Primary'
        primaryEmptyValue='--'
        primaryClassName='primary'
        secondary=''
        secondaryEmptyValue='--'
        secondaryClassName='secondary'
      />,
    );

    expect(screen.getAllByTestId('tooltip-text')).toHaveLength(1);
    expect(screen.getByText('Primary')).toHaveClass('primary');
  });

  test('renders the secondary line directly or wrapped', () => {
    const { rerender } = render(
      <StackedTooltipText
        primary='Primary'
        primaryEmptyValue='--'
        primaryClassName='primary'
        secondary='Secondary'
        secondaryEmptyValue='--'
        secondaryClassName='secondary'
      />,
    );
    const direct = screen.getByText('Secondary');
    expect(direct).toHaveClass('secondary');
    expect(direct.parentElement).toHaveClass('flex');

    rerender(
      <StackedTooltipText
        primary='Primary'
        primaryEmptyValue='--'
        primaryClassName='primary'
        secondary='Secondary'
        secondaryEmptyValue='--'
        secondaryClassName='secondary'
        wrapSecondary
      />,
    );
    expect(screen.getByText('Secondary').parentElement).toHaveClass(
      'text-xs',
      'text-muted-foreground',
    );
  });
});
