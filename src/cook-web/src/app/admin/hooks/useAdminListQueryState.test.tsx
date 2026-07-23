import { act, renderHook } from '@testing-library/react';
import { useAdminListQueryState } from './useAdminListQueryState';

type TestFilters = {
  keyword: string;
  status: string;
};

const DEFAULT_FILTERS: TestFilters = {
  keyword: '',
  status: '__all__',
};

describe('useAdminListQueryState', () => {
  test('applies draft filters and resets to the first page', () => {
    const { result } = renderHook(() =>
      useAdminListQueryState({
        defaultFilters: DEFAULT_FILTERS,
        initialPageCount: 4,
      }),
    );

    act(() => {
      result.current.goToPage(3);
      result.current.setDraftFilters(current => ({
        ...current,
        keyword: 'teacher',
      }));
    });

    expect(result.current.pageIndex).toBe(3);
    expect(result.current.appliedFilters.keyword).toBe('');
    expect(result.current.draftFilters.keyword).toBe('teacher');

    act(() => {
      result.current.applyDraftFilters();
    });

    expect(result.current.pageIndex).toBe(1);
    expect(result.current.appliedFilters.keyword).toBe('teacher');
  });

  test('resets draft and applied filters back to defaults', () => {
    const { result } = renderHook(() =>
      useAdminListQueryState({
        defaultFilters: DEFAULT_FILTERS,
        initialPageCount: 3,
      }),
    );

    act(() => {
      result.current.setDraftFilters({
        keyword: '13800138000',
        status: 'past_due',
      });
      result.current.applyDraftFilters();
      result.current.goToPage(2);
    });

    act(() => {
      result.current.resetFilters();
    });

    expect(result.current.pageIndex).toBe(1);
    expect(result.current.draftFilters).toEqual(DEFAULT_FILTERS);
    expect(result.current.appliedFilters).toEqual(DEFAULT_FILTERS);
  });

  test('syncs draft and applied filters together for quick filter flows', () => {
    const { result } = renderHook(() =>
      useAdminListQueryState({
        defaultFilters: DEFAULT_FILTERS,
      }),
    );

    act(() => {
      result.current.syncFilters(current => ({
        ...current,
        status: 'active',
      }));
    });

    expect(result.current.draftFilters.status).toBe('active');
    expect(result.current.appliedFilters.status).toBe('active');
    expect(result.current.pageIndex).toBe(1);
  });

  test('tracks the latest request token', () => {
    const { result } = renderHook(() =>
      useAdminListQueryState({
        defaultFilters: DEFAULT_FILTERS,
      }),
    );

    let firstRequestId = 0;
    let secondRequestId = 0;
    act(() => {
      firstRequestId = result.current.nextRequestId();
      secondRequestId = result.current.nextRequestId();
    });

    expect(result.current.isLatestRequest(firstRequestId)).toBe(false);
    expect(result.current.isLatestRequest(secondRequestId)).toBe(true);
  });
});
