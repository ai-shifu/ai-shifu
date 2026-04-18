import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { AdminPagination } from './AdminPagination';

describe('AdminPagination', () => {
  test('hides pagination when only one page is available', () => {
    render(
      <AdminPagination
        pageIndex={1}
        pageCount={1}
        onPageChange={jest.fn()}
        prevLabel='Previous'
        nextLabel='Next'
        hideWhenSinglePage
      />,
    );

    expect(
      screen.queryByRole('navigation', { name: 'pagination' }),
    ).not.toBeInTheDocument();
  });

  test('disables previous on the first page and moves forward', () => {
    const onPageChange = jest.fn();

    render(
      <AdminPagination
        pageIndex={1}
        pageCount={6}
        onPageChange={onPageChange}
        prevLabel='Previous'
        nextLabel='Next'
      />,
    );

    const previousLink = screen.getByRole('link', { name: /previous/i });
    const nextLink = screen.getByRole('link', { name: /next/i });

    expect(previousLink).toHaveAttribute('aria-disabled', 'true');

    fireEvent.click(previousLink);
    fireEvent.click(nextLink);

    expect(onPageChange).toHaveBeenCalledTimes(1);
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  test('renders condensed page links around the current page', () => {
    render(
      <AdminPagination
        pageIndex={5}
        pageCount={10}
        onPageChange={jest.fn()}
        prevLabel='Previous'
        nextLabel='Next'
      />,
    );

    expect(screen.getByRole('link', { name: '1' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '4' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '5' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: '6' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '10' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '2' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '8' })).not.toBeInTheDocument();
  });

  test('disables next on the last page and still allows jumping backward', () => {
    const onPageChange = jest.fn();

    render(
      <AdminPagination
        pageIndex={10}
        pageCount={10}
        onPageChange={onPageChange}
        prevLabel='Previous'
        nextLabel='Next'
      />,
    );

    const nextLink = screen.getByRole('link', { name: /next/i });

    expect(nextLink).toHaveAttribute('aria-disabled', 'true');

    fireEvent.click(nextLink);
    fireEvent.click(screen.getByRole('link', { name: '9' }));

    expect(onPageChange).toHaveBeenCalledTimes(1);
    expect(onPageChange).toHaveBeenCalledWith(9);
  });

  test('renders a simple two-page navigation without ellipsis or duplicate links', () => {
    const onPageChange = jest.fn();

    render(
      <AdminPagination
        pageIndex={1}
        pageCount={2}
        onPageChange={onPageChange}
        prevLabel='Previous'
        nextLabel='Next'
      />,
    );

    expect(screen.getAllByRole('link', { name: '1' })).toHaveLength(1);
    expect(screen.getAllByRole('link', { name: '2' })).toHaveLength(1);
    expect(
      screen.queryByText((_, element) => element?.textContent === 'More pages'),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: '1' }));
    fireEvent.click(screen.getByRole('link', { name: '2' }));

    expect(onPageChange).toHaveBeenCalledTimes(1);
    expect(onPageChange).toHaveBeenCalledWith(2);
  });
});
