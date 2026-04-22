import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { AppPagination } from './AppPagination';

describe('AppPagination', () => {
  test('hides pagination when only one page is available', () => {
    render(
      <AppPagination
        pageIndex={1}
        pageCount={1}
        onPageChange={jest.fn()}
        prevLabel='Previous'
        nextLabel='Next'
        prevAriaLabel='Go to previous page'
        nextAriaLabel='Go to next page'
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
      <AppPagination
        pageIndex={1}
        pageCount={6}
        onPageChange={onPageChange}
        prevLabel='Previous'
        nextLabel='Next'
        prevAriaLabel='Go to previous page'
        nextAriaLabel='Go to next page'
      />,
    );

    const previousLink = screen.getByRole('link', { name: /previous/i });
    const nextLink = screen.getByRole('link', { name: /next/i });

    expect(previousLink).toHaveAttribute('aria-disabled', 'true');
    expect(previousLink).toHaveAttribute('tabindex', '-1');
    expect(previousLink).toHaveAttribute('aria-label', 'Go to previous page');

    fireEvent.click(previousLink);
    fireEvent.click(nextLink);

    expect(onPageChange).toHaveBeenCalledTimes(1);
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  test('renders condensed page links around the current page', () => {
    render(
      <AppPagination
        pageIndex={5}
        pageCount={10}
        onPageChange={jest.fn()}
        prevLabel='Previous'
        nextLabel='Next'
        prevAriaLabel='Go to previous page'
        nextAriaLabel='Go to next page'
      />,
    );

    expect(screen.getByRole('link', { name: '1' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '4' })).toBeInTheDocument();
    const currentPageLink = screen.getByRole('link', { name: '5' });
    expect(currentPageLink).toHaveAttribute('aria-current', 'page');
    expect(currentPageLink).toHaveAttribute('tabindex', '-1');
    expect(currentPageLink).toHaveClass('pointer-events-none');
    expect(screen.getByRole('link', { name: '6' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '10' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '2' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '8' })).not.toBeInTheDocument();
  });

  test('disables next on the last page and still allows jumping backward', () => {
    const onPageChange = jest.fn();

    render(
      <AppPagination
        pageIndex={10}
        pageCount={10}
        onPageChange={onPageChange}
        prevLabel='Previous'
        nextLabel='Next'
        prevAriaLabel='Go to previous page'
        nextAriaLabel='Go to next page'
      />,
    );

    const nextLink = screen.getByRole('link', { name: /next/i });

    expect(nextLink).toHaveAttribute('aria-disabled', 'true');
    expect(nextLink).toHaveAttribute('tabindex', '-1');
    expect(nextLink).toHaveAttribute('aria-label', 'Go to next page');

    fireEvent.click(nextLink);
    fireEvent.click(screen.getByRole('link', { name: '9' }));

    expect(onPageChange).toHaveBeenCalledTimes(1);
    expect(onPageChange).toHaveBeenCalledWith(9);
  });

  test('renders a simple two-page navigation without ellipsis or duplicate links', () => {
    const onPageChange = jest.fn();

    render(
      <AppPagination
        pageIndex={1}
        pageCount={2}
        onPageChange={onPageChange}
        prevLabel='Previous'
        nextLabel='Next'
        prevAriaLabel='Go to previous page'
        nextAriaLabel='Go to next page'
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

  test('falls back to page 1 when page props are not finite numbers', () => {
    render(
      <AppPagination
        pageIndex={Number.NaN}
        pageCount={Number.NaN}
        onPageChange={jest.fn()}
        prevLabel='Previous'
        nextLabel='Next'
        prevAriaLabel='Go to previous page'
        nextAriaLabel='Go to next page'
      />,
    );

    const currentPageLink = screen.getByRole('link', { name: '1' });
    expect(currentPageLink).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('link', { name: 'NaN' })).not.toBeInTheDocument();
  });
});
