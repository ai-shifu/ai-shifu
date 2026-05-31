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
});
