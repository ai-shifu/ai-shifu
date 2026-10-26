import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminOperationUserCreditFilters,
  AdminOperationUserCreditsResponse,
} from '../../operation-user-types';
import {
  createUserCreditFilters,
  FILTER_ALL_OPTION,
  sanitizeCreditFiltersByType,
} from './creditFilterUtils';
import {
  CREDITS_PAGE_SIZE,
  createEmptyCreditsResponse,
  type ErrorState,
} from './userDetailConstants';

type UseUserCreditLedgerDataOptions = {
  isReady: boolean;
  userBid: string;
  userBidErrorMessage: string;
};

const areCreditFiltersEqual = (
  left: AdminOperationUserCreditFilters,
  right: AdminOperationUserCreditFilters,
) =>
  left.creditType === right.creditType &&
  left.grantSource === right.grantSource &&
  left.courseQuery === right.courseQuery &&
  left.usageScene === right.usageScene &&
  left.usageMode === right.usageMode &&
  left.startTime === right.startTime &&
  left.endTime === right.endTime;

export default function useUserCreditLedgerData({
  isReady,
  userBid,
  userBidErrorMessage,
}: UseUserCreditLedgerDataOptions) {
  const { t } = useTranslation();
  const hasInitializedCreditStateRef = useRef(false);
  const [creditsLoading, setCreditsLoading] = useState(true);
  const [creditsError, setCreditsError] = useState<ErrorState | null>(null);
  const [creditsRetryNonce, setCreditsRetryNonce] = useState(0);
  const [creditsPageIndex, setCreditsPageIndex] = useState(1);
  const [creditFiltersDraft, setCreditFiltersDraft] =
    useState<AdminOperationUserCreditFilters>(createUserCreditFilters);
  const [creditFilters, setCreditFilters] =
    useState<AdminOperationUserCreditFilters>(createUserCreditFilters);
  const [credits, setCredits] = useState<AdminOperationUserCreditsResponse>(
    createEmptyCreditsResponse,
  );

  useEffect(() => {
    if (!hasInitializedCreditStateRef.current) {
      hasInitializedCreditStateRef.current = true;
      return;
    }
    setCreditsPageIndex(1);
    setCreditsError(null);
    setCredits(createEmptyCreditsResponse());
    setCreditFiltersDraft(createUserCreditFilters());
    setCreditFilters(createUserCreditFilters());
  }, [userBid]);

  useEffect(() => {
    if (!isReady || !userBid || userBidErrorMessage) {
      return;
    }

    let cancelled = false;

    const fetchCredits = async () => {
      setCreditsLoading(true);
      setCreditsError(null);
      try {
        const response = (await api.getAdminOperationUserCredits({
          user_bid: userBid,
          page_index: creditsPageIndex,
          page_size: CREDITS_PAGE_SIZE,
          credit_type:
            creditFilters.creditType === FILTER_ALL_OPTION
              ? ''
              : creditFilters.creditType,
          grant_source:
            creditFilters.creditType === 'grant' &&
            creditFilters.grantSource !== FILTER_ALL_OPTION
              ? creditFilters.grantSource
              : '',
          course_query:
            creditFilters.creditType === 'consume'
              ? creditFilters.courseQuery.trim()
              : '',
          usage_scene:
            creditFilters.creditType === 'consume' &&
            creditFilters.usageScene !== FILTER_ALL_OPTION
              ? creditFilters.usageScene
              : '',
          usage_mode:
            creditFilters.creditType === 'consume' &&
            creditFilters.usageMode !== FILTER_ALL_OPTION
              ? creditFilters.usageMode
              : '',
          start_time:
            creditFilters.creditType !== FILTER_ALL_OPTION
              ? creditFilters.startTime
              : '',
          end_time:
            creditFilters.creditType !== FILTER_ALL_OPTION
              ? creditFilters.endTime
              : '',
        })) as AdminOperationUserCreditsResponse;
        if (cancelled) {
          return;
        }
        setCredits(response);
      } catch (requestError) {
        if (cancelled) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setCreditsError({
          message: resolvedError.message || t('common.core.networkError'),
          code: resolvedError.code,
        });
        setCredits(current => ({
          ...current,
          items: [],
          page: creditsPageIndex,
          page_count: 0,
          total: 0,
        }));
      } finally {
        if (!cancelled) {
          setCreditsLoading(false);
        }
      }
    };

    void fetchCredits();

    return () => {
      cancelled = true;
    };
  }, [
    creditsPageIndex,
    creditFilters,
    creditsRetryNonce,
    isReady,
    t,
    userBid,
    userBidErrorMessage,
  ]);

  const handleCreditSearch = useCallback(() => {
    const nextFilters = sanitizeCreditFiltersByType({
      ...creditFiltersDraft,
      courseQuery: creditFiltersDraft.courseQuery.trim(),
    });
    setCreditFiltersDraft(nextFilters);
    setCreditFilters(nextFilters);
    setCreditsPageIndex(1);
  }, [creditFiltersDraft]);

  const handleCreditTypeChange = useCallback(
    (nextFilters: AdminOperationUserCreditFilters) => {
      const sanitizedFilters = sanitizeCreditFiltersByType({
        ...nextFilters,
        courseQuery: nextFilters.courseQuery.trim(),
      });
      setCreditFiltersDraft(sanitizedFilters);
      setCreditFilters(sanitizedFilters);
      setCreditsPageIndex(1);
    },
    [],
  );

  const handleCreditReset = useCallback(() => {
    const nextFilters = createUserCreditFilters();
    if (
      areCreditFiltersEqual(creditFiltersDraft, nextFilters) &&
      areCreditFiltersEqual(creditFilters, nextFilters) &&
      creditsPageIndex === 1
    ) {
      return;
    }
    setCreditFiltersDraft(nextFilters);
    setCreditFilters(nextFilters);
    setCreditsPageIndex(1);
  }, [creditFilters, creditFiltersDraft, creditsPageIndex]);

  const retryCredits = useCallback(() => {
    setCreditsRetryNonce(value => value + 1);
  }, []);

  return {
    credits,
    creditsLoading,
    creditsError,
    creditsPageIndex,
    creditFilters,
    creditFiltersDraft,
    setCreditFiltersDraft,
    setCreditsPageIndex,
    handleCreditSearch,
    handleCreditTypeChange,
    handleCreditReset,
    retryCredits,
  };
}
