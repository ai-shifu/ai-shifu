import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { ErrorWithCode } from '@/lib/request';
import type { AdminOperationUserDetailResponse } from '../../operation-user-types';
import { EMPTY_DETAIL, type ErrorState } from './userDetailConstants';

type UseUserDetailDataOptions = {
  isReady: boolean;
  rawUserBid?: string;
};

export default function useUserDetailData({
  isReady,
  rawUserBid,
}: UseUserDetailDataOptions) {
  const { t } = useTranslation();
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<ErrorState | null>(null);
  const [detailRetryNonce, setDetailRetryNonce] = useState(0);
  const [detail, setDetail] =
    useState<AdminOperationUserDetailResponse>(EMPTY_DETAIL);

  const userBidState = useMemo(() => {
    const normalizedRawUserBid = String(rawUserBid || '').trim();
    if (!normalizedRawUserBid) {
      return {
        userBid: '',
        errorMessage: t('server.common.paramsError'),
      };
    }

    try {
      return {
        userBid: decodeURIComponent(normalizedRawUserBid),
        errorMessage: '',
      };
    } catch {
      return {
        userBid: '',
        errorMessage: t('server.common.paramsError'),
      };
    }
  }, [rawUserBid, t]);

  useEffect(() => {
    if (!isReady) {
      return;
    }

    if (userBidState.errorMessage) {
      setDetailError({ message: userBidState.errorMessage });
      setDetailLoading(false);
      return;
    }

    let cancelled = false;

    const fetchDetail = async () => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const response = (await api.getAdminOperationUserDetail({
          user_bid: userBidState.userBid,
        })) as AdminOperationUserDetailResponse;
        if (cancelled) {
          return;
        }
        setDetail(response);
      } catch (requestError) {
        if (cancelled) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setDetailError({
          message: resolvedError.message || t('common.core.networkError'),
          code: resolvedError.code,
        });
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    };

    void fetchDetail();

    return () => {
      cancelled = true;
    };
  }, [
    detailRetryNonce,
    isReady,
    t,
    userBidState.errorMessage,
    userBidState.userBid,
  ]);

  const retryDetail = useCallback(() => {
    setDetailRetryNonce(value => value + 1);
  }, []);

  return {
    detail,
    detailLoading,
    detailError,
    retryDetail,
    userBid: userBidState.userBid,
    userBidErrorMessage: userBidState.errorMessage,
  };
}
