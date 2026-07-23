import { useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { buildBillingSwrKey } from '@/lib/billing';
import type { BillingPagedResponse } from '@/types/billing';

type BillingAdminPagedQueryParams<T> = {
  fetchPage: (params: {
    page_index: number;
    page_size: number;
  }) => Promise<BillingPagedResponse<T>>;
  pageSize: number;
  queryKey: string;
  queryDeps?: Array<string | number | boolean | null | undefined>;
};

export function useBillingAdminPagedQuery<T>({
  fetchPage,
  pageSize,
  queryKey,
  queryDeps = [],
}: BillingAdminPagedQueryParams<T>) {
  const [pageIndex, setPageIndex] = useState(1);
  const normalizedDeps = useMemo(
    () => queryDeps.map(value => String(value ?? '')),
    [queryDeps],
  );
  const depsKey = normalizedDeps.join('\u0001');
  const lastDepsKeyRef = useRef(depsKey);

  useEffect(() => {
    if (lastDepsKeyRef.current === depsKey) {
      return;
    }
    lastDepsKeyRef.current = depsKey;
    setPageIndex(1);
  }, [depsKey]);

  const { data, error, isLoading } = useSWR<BillingPagedResponse<T>>(
    buildBillingSwrKey(queryKey, pageIndex, ...normalizedDeps),
    async () =>
      fetchPage({
        page_index: pageIndex,
        page_size: pageSize,
      }),
    {
      revalidateOnFocus: false,
    },
  );

  const page = Number(data?.page || pageIndex);
  const pageCount = Number(data?.page_count || 1);
  const total = Number(data?.total || 0);

  return {
    data,
    error,
    isLoading,
    items: data?.items || [],
    page,
    pageCount,
    total,
    canGoPrev: page > 1,
    canGoNext: page < pageCount,
    goPrev: () => setPageIndex(current => Math.max(1, current - 1)),
    goNext: () => setPageIndex(current => Math.min(pageCount, current + 1)),
    setPage: (nextPage: number) => setPageIndex(Math.max(1, nextPage)),
  };
}
