import React from 'react';
import { render, screen } from '@testing-library/react';
import AdminFilter, { type AdminFilterItem } from './AdminFilter';

const renderFilter = ({
  expanded = false,
  items,
}: {
  expanded?: boolean;
  items?: AdminFilterItem[];
} = {}) =>
  render(
    <AdminFilter
      items={
        items ?? [
          {
            key: 'type',
            label: 'Type',
            component: <input aria-label='Type filter' />,
          },
          {
            key: 'course',
            label: 'Course',
            component: <input aria-label='Course filter' />,
          },
          {
            key: 'status',
            label: 'Status',
            component: <input aria-label='Status filter' />,
          },
        ]
      }
      expanded={expanded}
      onExpandedChange={() => undefined}
      onReset={() => undefined}
      onSearch={() => undefined}
      resetLabel='Reset'
      searchLabel='Search'
      expandLabel='Expand'
      collapseLabel='Collapse'
      collapsedCount={2}
      collapsedGridClassName='collapsed-grid-test'
      expandedGridClassName='expanded-grid-test'
      labelColon
    />,
  );

describe('AdminFilter', () => {
  test('applies the label colon class when enabled', () => {
    renderFilter();

    expect(screen.getByText('Type')).toHaveClass("after:content-[':']");
  });

  test('applies collapsed grid classes and limits the visible fields', () => {
    const { container } = renderFilter();

    expect(container.querySelector('.collapsed-grid-test')).toBeInTheDocument();
    expect(
      container.querySelector('.expanded-grid-test'),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText('Type filter')).toBeInTheDocument();
    expect(screen.getByLabelText('Course filter')).toBeInTheDocument();
    expect(screen.queryByLabelText('Status filter')).not.toBeInTheDocument();
  });

  test('applies expanded grid classes and renders all fields', () => {
    const { container } = renderFilter({ expanded: true });

    expect(container.querySelector('.expanded-grid-test')).toBeInTheDocument();
    expect(
      container.querySelector('.collapsed-grid-test'),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText('Type filter')).toBeInTheDocument();
    expect(screen.getByLabelText('Course filter')).toBeInTheDocument();
    expect(screen.getByLabelText('Status filter')).toBeInTheDocument();
  });
});
