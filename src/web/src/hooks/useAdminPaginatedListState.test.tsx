import { act, renderHook } from '@testing-library/react';
import { useAdminPaginatedListState } from './useAdminPaginatedListState';

describe('useAdminPaginatedListState', () => {
  test('tracks page changes within bounds', () => {
    const onPageChange = jest.fn();
    const { result } = renderHook(() =>
      useAdminPaginatedListState({
        initialPageCount: 3,
        onPageChange,
      }),
    );

    expect(result.current.pageIndex).toBe(1);
    expect(result.current.pageCount).toBe(3);

    act(() => {
      result.current.goToPage(2);
    });

    expect(result.current.pageIndex).toBe(2);
    expect(onPageChange).toHaveBeenCalledWith(2);

    act(() => {
      result.current.goToPage(99);
    });

    expect(result.current.pageIndex).toBe(3);
    expect(onPageChange).toHaveBeenLastCalledWith(3);
  });

  test('ignores same-page navigation and invalid page values', () => {
    const onPageChange = jest.fn();
    const { result } = renderHook(() =>
      useAdminPaginatedListState({
        initialPageCount: 3,
        onPageChange,
      }),
    );

    act(() => {
      result.current.goToPage(1);
      result.current.goToPage(Number.NaN);
    });

    expect(result.current.pageIndex).toBe(1);
    expect(onPageChange).not.toHaveBeenCalled();
  });

  test('clamps the current page when page count shrinks', () => {
    const { result } = renderHook(() =>
      useAdminPaginatedListState({
        initialPageCount: 5,
      }),
    );

    act(() => {
      result.current.goToPage(5);
    });
    expect(result.current.pageIndex).toBe(5);

    act(() => {
      result.current.setPageCount(2);
    });

    expect(result.current.pageCount).toBe(2);
    expect(result.current.pageIndex).toBe(2);
  });

  test('resets to the first page', () => {
    const { result } = renderHook(() =>
      useAdminPaginatedListState({
        initialPageCount: 3,
      }),
    );

    act(() => {
      result.current.goToPage(2);
    });
    expect(result.current.pageIndex).toBe(2);

    act(() => {
      result.current.resetPage();
    });

    expect(result.current.pageIndex).toBe(1);
  });
});
