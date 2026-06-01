import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AdminFilter, {
  type AdminFilterActiveFilter,
  type AdminFilterItem,
} from './AdminFilter';

const renderFilter = ({
  expanded = false,
  items,
  activeFilter,
  layoutPreset,
  surface,
}: {
  expanded?: boolean;
  items?: AdminFilterItem[];
  activeFilter?: AdminFilterActiveFilter | null;
  layoutPreset?: 'default' | 'operations';
  surface?: 'plain' | 'card';
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
      activeFilter={activeFilter}
      layoutPreset={layoutPreset}
      surface={surface}
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

  test('renders the card surface and active filter chip', () => {
    const onClear = jest.fn();
    const { container } = renderFilter({
      surface: 'card',
      activeFilter: {
        label: 'Active filter',
        value: 'Recent courses',
        clearAriaLabel: 'Clear recent courses',
        onClear,
      },
    });

    expect(container.firstChild).toHaveClass('rounded-xl');
    expect(screen.getByText('Active filter')).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'Clear recent courses' }),
    );

    expect(onClear).toHaveBeenCalledTimes(1);
  });

  test('applies operations preset defaults when custom classes are not provided', () => {
    const { container } = render(
      <AdminFilter
        items={[
          {
            key: 'type',
            label: 'Type',
            component: <input aria-label='Type filter' />,
          },
        ]}
        expanded={false}
        onExpandedChange={() => undefined}
        onReset={() => undefined}
        onSearch={() => undefined}
        resetLabel='Reset'
        searchLabel='Search'
        expandLabel='Expand'
        collapseLabel='Collapse'
        layoutPreset='operations'
      />,
    );

    expect(screen.getByText('Type')).toHaveClass("after:content-[':']");
    expect(screen.getByText('Type')).toHaveClass('w-20');
    expect(container.querySelector('.xl\\:grid-cols-3')).toBeInTheDocument();
  });
});
