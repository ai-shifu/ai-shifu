'use client';

import * as React from 'react';
import { useAdminPaginatedListState } from './useAdminPaginatedListState';

type StateUpdater<T> = T | ((current: T) => T);

type UseAdminListQueryStateOptions<TFilters> = {
  defaultFilters: TFilters;
  initialAppliedFilters?: TFilters;
  initialDraftFilters?: TFilters;
  initialPageCount?: number;
  initialPageIndex?: number;
  onPageChange?: (nextPage: number) => void;
};

const resolveNextState = <T>(current: T, nextState: StateUpdater<T>): T => {
  if (typeof nextState === 'function') {
    return (nextState as (value: T) => T)(current);
  }
  return nextState;
};

export function useAdminListQueryState<TFilters>({
  defaultFilters,
  initialAppliedFilters,
  initialDraftFilters,
  initialPageCount,
  initialPageIndex,
  onPageChange,
}: UseAdminListQueryStateOptions<TFilters>) {
  const [draftFilters, setDraftFiltersState] = React.useState<TFilters>(
    () => initialDraftFilters ?? initialAppliedFilters ?? defaultFilters,
  );
  const [appliedFilters, setAppliedFiltersState] = React.useState<TFilters>(
    () => initialAppliedFilters ?? defaultFilters,
  );
  const { pageIndex, pageCount, setPageCount, goToPage, resetPage } =
    useAdminPaginatedListState({
      initialPageCount,
      initialPageIndex,
      onPageChange,
    });
  const latestRequestIdRef = React.useRef(0);

  const setDraftFilters = React.useCallback(
    (nextState: StateUpdater<TFilters>) => {
      setDraftFiltersState(current => resolveNextState(current, nextState));
    },
    [],
  );

  const setAppliedFilters = React.useCallback(
    (nextState: StateUpdater<TFilters>) => {
      setAppliedFiltersState(current => resolveNextState(current, nextState));
    },
    [],
  );

  const applyDraftFilters = React.useCallback(() => {
    setAppliedFiltersState(draftFilters);
    resetPage();
  }, [draftFilters, resetPage]);

  const resetFilters = React.useCallback(() => {
    setDraftFiltersState(defaultFilters);
    setAppliedFiltersState(defaultFilters);
    resetPage();
  }, [defaultFilters, resetPage]);

  const syncFilters = React.useCallback(
    (nextState: StateUpdater<TFilters>) => {
      const nextFilters = resolveNextState(draftFilters, nextState);
      setDraftFiltersState(nextFilters);
      setAppliedFiltersState(nextFilters);
      resetPage();
    },
    [draftFilters, resetPage],
  );

  const nextRequestId = React.useCallback(() => {
    latestRequestIdRef.current += 1;
    return latestRequestIdRef.current;
  }, []);

  const isLatestRequest = React.useCallback((requestId: number) => {
    return requestId === latestRequestIdRef.current;
  }, []);

  return {
    draftFilters,
    appliedFilters,
    pageIndex,
    pageCount,
    setPageCount,
    setDraftFilters,
    setAppliedFilters,
    applyDraftFilters,
    resetFilters,
    syncFilters,
    goToPage,
    resetPage,
    nextRequestId,
    isLatestRequest,
  };
}
