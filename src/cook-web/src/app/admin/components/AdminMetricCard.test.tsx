import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { AdminMetricCardGroup } from './AdminMetricCard';

describe('AdminMetricCardGroup', () => {
  test('renders the titled card group and handles metric clicks', () => {
    const onClick = jest.fn();

    render(
      <AdminMetricCardGroup
        title='Data overview'
        items={[
          {
            key: 'total',
            label: 'Total courses',
            value: '18',
            tooltip: 'All course records',
            onClick,
          },
        ]}
      />,
    );

    expect(screen.getByText('Data overview')).toBeInTheDocument();
    expect(screen.getByText('Total courses')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Total courses' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  test('supports inset control hover mode without changing tooltip labels', () => {
    render(
      <AdminMetricCardGroup
        items={[
          {
            key: 'pending',
            label: 'Pending notifications',
            value: 12,
            tooltip: 'Pending notification records',
            onClick: jest.fn(),
          },
        ]}
        cardHoverMode='control'
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Pending notifications' }),
    ).toHaveClass('-m-2');
    expect(
      screen.getByRole('button', { name: 'Pending notification records' }),
    ).toBeInTheDocument();
  });

  test('applies className when the group has no title', () => {
    const { container } = render(
      <AdminMetricCardGroup
        className='metric-group-wrapper'
        items={[
          {
            key: 'sent',
            label: 'Sent notifications',
            value: 8,
            tooltip: 'Sent notification records',
          },
        ]}
      />,
    );

    expect(container.firstChild).toHaveClass('metric-group-wrapper');
  });

  test('keeps card hover on non-clickable card-mode metrics', () => {
    render(
      <AdminMetricCardGroup
        items={[
          {
            key: 'paid',
            label: 'Paid amount',
            value: '$18',
            tooltip: 'Total paid amount',
          },
        ]}
      />,
    );

    expect(screen.getByText('Paid amount').closest('.rounded-lg')).toHaveClass(
      'hover:border-primary/30',
    );
  });

  test('limits clickable card-mode hover to the metric control', () => {
    render(
      <AdminMetricCardGroup
        items={[
          {
            key: 'failed',
            label: 'Failed notifications',
            value: 2,
            tooltip: 'Failed notification records',
            onClick: jest.fn(),
          },
        ]}
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Failed notifications' }),
    ).toHaveClass('metric-control');
    expect(
      screen.getByText('Failed notifications').closest('.rounded-lg'),
    ).toHaveClass('has-[.metric-control:hover]:border-primary/30');
  });
});
