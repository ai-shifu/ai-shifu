'use client';

import * as React from 'react';

type UseAdminPaginatedListStateOptions = {
  initialPageIndex?: number;
  initialPageCount?: number;
  onPageChange?: (nextPage: number) => void;
};

const normalizePageValue = (value: number | undefined, fallback: number) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.max(1, Math.floor(value));
};

export function useAdminPaginatedListState({
  initialPageIndex = 1,
  initialPageCount = 1,
  onPageChange,
}: UseAdminPaginatedListStateOptions = {}) {
  const [pageIndex, setPageIndexState] = React.useState(() =>
    normalizePageValue(initialPageIndex, 1),
  );
  const [pageCount, setPageCountState] = React.useState(() =>
    normalizePageValue(initialPageCount, 1),
  );

  const setPageCount = React.useCallback((nextPageCount: number) => {
    const normalizedPageCount = normalizePageValue(nextPageCount, 1);
    setPageCountState(normalizedPageCount);
    setPageIndexState(currentPageIndex =>
      Math.min(currentPageIndex, normalizedPageCount),
    );
  }, []);

  const goToPage = React.useCallback(
    (nextPage: number) => {
      setPageIndexState(currentPageIndex => {
        const normalizedNextPage = normalizePageValue(nextPage, currentPageIndex);
        const clampedNextPage = Math.min(normalizedNextPage, pageCount);
        if (clampedNextPage === currentPageIndex) {
          return currentPageIndex;
        }
        onPageChange?.(clampedNextPage);
        return clampedNextPage;
      });
    },
    [onPageChange, pageCount],
  );

  const resetPage = React.useCallback(() => {
    goToPage(1);
  }, [goToPage]);

  return {
    pageIndex,
    pageCount,
    setPageCount,
    goToPage,
    resetPage,
  };
}
