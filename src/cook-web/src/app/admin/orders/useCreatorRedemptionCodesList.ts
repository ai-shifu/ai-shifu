'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import api from '@/api';
import type {
  AdminPromotionCouponItem,
  AdminPromotionListResponse,
} from '@/app/admin/operations/operation-promotion-types';
import {
  createDefaultFilters,
  PAGE_SIZE,
  type RedemptionCodeFilters,
} from './creatorRedemptionCodeShared';

type TranslationFn = (key: string, options?: Record<string, unknown>) => string;

type RedemptionListError = {
  message: string;
};

export const useCreatorRedemptionCodesList = ({
  reloadKey,
  t,
}: {
  reloadKey: number;
  t: TranslationFn;
}) => {
  const [filters, setFilters] = useState<RedemptionCodeFilters>(() =>
    createDefaultFilters(),
  );
  const filtersRef = useRef<RedemptionCodeFilters>(filters);
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<AdminPromotionCouponItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<RedemptionListError | null>(null);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [total, setTotal] = useState(0);
  const fetchRequestIdRef = useRef(0);

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  const fetchCodes = useCallback(
    async (targetPage: number, nextFilters?: RedemptionCodeFilters) => {
      const requestId = fetchRequestIdRef.current + 1;
      fetchRequestIdRef.current = requestId;
      const resolvedFilters = nextFilters ?? filtersRef.current;
      setLoading(true);
      setError(current => (current ? null : current));
      try {
        const response = (await api.getCreatorCourseRedemptionCodes({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          keyword: resolvedFilters.keyword.trim(),
          name: resolvedFilters.name.trim(),
          course_query: resolvedFilters.course_query.trim(),
          usage_type: resolvedFilters.usage_type,
          ops_state: resolvedFilters.ops_state,
          discount_type: resolvedFilters.discount_type,
          status: resolvedFilters.status,
          start_time: resolvedFilters.start_time,
          end_time: resolvedFilters.end_time,
        })) as AdminPromotionListResponse<AdminPromotionCouponItem>;

        if (requestId !== fetchRequestIdRef.current) {
          return;
        }
        setItems(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 1);
        setTotal(response.total || 0);
      } catch (err) {
        if (requestId !== fetchRequestIdRef.current) {
          return;
        }
        setItems([]);
        setPageIndex(targetPage);
        setPageCount(1);
        setTotal(0);
        setError({
          message:
            err instanceof Error
              ? err.message
              : t('module.order.redemptionCodes.loadFailed'),
        });
      } finally {
        if (requestId === fetchRequestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [t],
  );

  useEffect(() => {
    void fetchCodes(1);
  }, [fetchCodes, reloadKey]);

  const handleFilterChange = useCallback(
    (key: keyof RedemptionCodeFilters, value: string) => {
      setFilters(current => ({ ...current, [key]: value }));
    },
    [],
  );

  const handleSearch = useCallback(() => {
    void fetchCodes(1, filtersRef.current);
  }, [fetchCodes]);

  const handleReset = useCallback(() => {
    const cleared = createDefaultFilters();
    setFilters(cleared);
    void fetchCodes(1, cleared);
  }, [fetchCodes]);

  const handlePageChange = useCallback(
    (nextPage: number) => {
      if (nextPage < 1 || nextPage > pageCount || nextPage === pageIndex) {
        return;
      }
      void fetchCodes(nextPage);
    },
    [fetchCodes, pageCount, pageIndex],
  );

  return {
    error,
    expanded,
    fetchCodes,
    filters,
    filtersRef,
    handleFilterChange,
    handlePageChange,
    handleReset,
    handleSearch,
    items,
    loading,
    pageCount,
    pageIndex,
    setExpanded,
    total,
  };
};
