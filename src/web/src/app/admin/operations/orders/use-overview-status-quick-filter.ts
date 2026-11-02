import * as React from 'react';

type FiltersWithStatus = {
  status: string;
};

type UseOverviewStatusQuickFilterOptions<TFilters extends FiltersWithStatus> = {
  appliedFilters: TFilters;
  setDraftFilters: React.Dispatch<React.SetStateAction<TFilters>>;
  setAppliedFilters: React.Dispatch<React.SetStateAction<TFilters>>;
  setPageIndex: React.Dispatch<React.SetStateAction<number>>;
};

export function useOverviewStatusQuickFilter<
  TFilters extends FiltersWithStatus,
>({
  appliedFilters,
  setDraftFilters,
  setAppliedFilters,
  setPageIndex,
}: UseOverviewStatusQuickFilterOptions<TFilters>) {
  const [activeOverviewStatus, setActiveOverviewStatus] = React.useState<
    string | null
  >(null);
  const [overviewStatusBeforeApply, setOverviewStatusBeforeApply] =
    React.useState<string | null>(null);

  const resetOverviewQuickFilterState = React.useCallback(() => {
    setActiveOverviewStatus(null);
    setOverviewStatusBeforeApply(null);
  }, []);

  const applyStatusQuickFilter = React.useCallback(
    (status: string) => {
      if (activeOverviewStatus === status) {
        return;
      }

      if (activeOverviewStatus === null) {
        setOverviewStatusBeforeApply(appliedFilters.status || null);
      }

      if (appliedFilters.status === status) {
        setActiveOverviewStatus(status);
        setDraftFilters(current =>
          current.status === status
            ? current
            : {
                ...current,
                status,
              },
        );
        return;
      }

      const nextFilters = {
        ...appliedFilters,
        status,
      };
      setActiveOverviewStatus(status);
      setDraftFilters(nextFilters);
      setAppliedFilters(nextFilters);
      setPageIndex(1);
    },
    [
      activeOverviewStatus,
      appliedFilters,
      setAppliedFilters,
      setDraftFilters,
      setPageIndex,
    ],
  );

  const clearOverviewQuickFilter = React.useCallback(() => {
    if (activeOverviewStatus === null) {
      return;
    }

    const restoredStatus = overviewStatusBeforeApply ?? '';
    resetOverviewQuickFilterState();
    setDraftFilters(current =>
      current.status === restoredStatus
        ? current
        : {
            ...current,
            status: restoredStatus,
          },
    );

    if (appliedFilters.status === restoredStatus) {
      return;
    }

    const nextFilters = {
      ...appliedFilters,
      status: restoredStatus,
    };
    setAppliedFilters(nextFilters);
    setPageIndex(1);
  }, [
    activeOverviewStatus,
    appliedFilters,
    overviewStatusBeforeApply,
    resetOverviewQuickFilterState,
    setAppliedFilters,
    setDraftFilters,
    setPageIndex,
  ]);

  return {
    activeOverviewStatus,
    applyStatusQuickFilter,
    clearOverviewQuickFilter,
    resetOverviewQuickFilterState,
  };
}
