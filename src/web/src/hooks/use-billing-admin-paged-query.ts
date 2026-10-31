import { useMemo } from 'react';
import useSWR from 'swr';
import { buildBillingSwrKey } from '@/lib/billing';
import type { BillingPagedResponse } from '@/types/billing';

type BillingAdminPagedQueryParams<T> = {
  fetchPage: (params: {
    page_index: number;
    page_size: number;
  }) => Promise<BillingPagedResponse<T>>;
  pageIndex: number;
  pageSize: number;
  queryKey: string;
  queryDeps?: Array<string | number | boolean | null | undefined>;
};

export function useBillingAdminPagedQuery<T>({
  fetchPage,
  pageIndex,
  pageSize,
  queryKey,
  queryDeps = [],
}: BillingAdminPagedQueryParams<T>) {
  const normalizedDeps = useMemo(
    () => queryDeps.map(value => String(value ?? '')),
    [queryDeps],
  );

  const { data, error, isLoading } = useSWR<BillingPagedResponse<T>>(
    buildBillingSwrKey(queryKey, pageIndex, ...normalizedDeps),
    async () =>
      fetchPage({
        page_index: pageIndex,
        page_size: pageSize,
      }),
    {
      keepPreviousData: true,
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
  };
}
