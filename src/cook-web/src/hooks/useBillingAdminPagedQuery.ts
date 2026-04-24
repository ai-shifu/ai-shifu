import { useState } from 'react';
import useSWR from 'swr';
import { buildBillingSwrKey, withBillingTimezone } from '@/lib/billing';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import type { BillingPagedResponse } from '@/types/billing';

type BillingAdminPagedQueryParams<T> = {
  fetchPage: (params: {
    page_index: number;
    page_size: number;
    timezone?: string;
  }) => Promise<BillingPagedResponse<T>>;
  pageSize: number;
  queryKey: string;
};

export function useBillingAdminPagedQuery<T>({
  fetchPage,
  pageSize,
  queryKey,
}: BillingAdminPagedQueryParams<T>) {
  const timezone = getBrowserTimeZone();
  const [pageIndex, setPageIndex] = useState(1);
  const { data, error, isLoading } = useSWR<BillingPagedResponse<T>>(
    buildBillingSwrKey(queryKey, timezone, pageIndex),
    async () =>
      fetchPage(
        withBillingTimezone(
          {
            page_index: pageIndex,
            page_size: pageSize,
          },
          timezone,
        ),
      ),
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
