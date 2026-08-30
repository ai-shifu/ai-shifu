'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { mutate as mutateSWRCache } from 'swr';
import api from '@/api';
import { useTracking } from '@/c-common/hooks/useTracking';
import { Button } from '@/components/ui/Button';
import { buildBillingSwrKey } from '@/lib/billing';
import {
  buildCreatorBillingResultAnalytics,
  buildCreatorBillingStatusAnalytics,
  CREATOR_BILLING_ANALYTICS_EVENTS,
  trackCreatorBillingEventSafely,
  type CreatorBillingFailureCategory,
} from '@/lib/billingAnalytics';
import request from '@/lib/request';
import { consumeStripeCheckoutSession } from '@/lib/stripe-storage';
import { useTranslation } from 'react-i18next';

type BillingResultStatus = 'loading' | 'success' | 'pending' | 'error';
const BILLING_OVERVIEW_SWR_KEY = 'creator-billing-overview';
const BILLING_WALLET_BUCKETS_SWR_KEY = 'billing-wallet-buckets';
const BILLING_RECENT_LEDGER_PAGE_INDEX = 1;
const BILLING_RECENT_LEDGER_PAGE_SIZE = 20;
const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;

type BillingSyncResponse = {
  status?: BillingOrderSyncStatus | string;
};

type BillingOrderSyncStatus =
  | 'paid'
  | 'pending'
  | 'failed'
  | 'canceled'
  | 'timeout'
  | 'refunded';

type StripeBillingResultMessageKey =
  | 'module.billing.result.missingOrder'
  | 'module.billing.result.processing'
  | 'module.billing.result.pending'
  | 'module.billing.result.success'
  | 'module.billing.result.errorTitle';

async function refreshBillingPageCaches() {
  await Promise.allSettled([
    mutateSWRCache(
      buildBillingSwrKey(BILLING_OVERVIEW_SWR_KEY),
      async () =>
        await api.getBillingOverview({}, BILLING_PASSIVE_REQUEST_CONFIG),
      { revalidate: false },
    ),
    mutateSWRCache(
      buildBillingSwrKey(BILLING_WALLET_BUCKETS_SWR_KEY),
      async () =>
        await api.getBillingWalletBuckets({}, BILLING_PASSIVE_REQUEST_CONFIG),
      { revalidate: false },
    ),
    mutateSWRCache(
      buildBillingSwrKey(
        'billing-ledger-recent',
        BILLING_RECENT_LEDGER_PAGE_INDEX,
        BILLING_RECENT_LEDGER_PAGE_SIZE,
      ),
      async () =>
        await api.getBillingLedger(
          {
            page_index: BILLING_RECENT_LEDGER_PAGE_INDEX,
            page_size: BILLING_RECENT_LEDGER_PAGE_SIZE,
          },
          BILLING_PASSIVE_REQUEST_CONFIG,
        ),
      { revalidate: false },
    ),
  ]);
}

type StripeBillingResultState = {
  status: BillingResultStatus;
  messageKey?: StripeBillingResultMessageKey;
  messageText?: string;
  billingOrderBid?: string;
};

export default function StripeBillingResultPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const [state, setState] = useState<StripeBillingResultState>({
    status: 'loading',
    messageKey: 'module.billing.result.processing',
  });
  const [redirectCountdown, setRedirectCountdown] = useState(3);
  const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const syncAttemptedRef = useRef<string | null>(null);
  const reportedAnalyticsKeysRef = useRef(new Set<string>());
  const providedBillingOrderBid = searchParams.get('bill_order_bid') || '';
  const sessionId = searchParams.get('session_id') || '';
  const canceled = searchParams.get('canceled') === '1';

  const billingOrderBid = useMemo(() => {
    if (providedBillingOrderBid) {
      return providedBillingOrderBid;
    }
    if (!sessionId) {
      return '';
    }
    return consumeStripeCheckoutSession(sessionId) || '';
  }, [providedBillingOrderBid, sessionId]);

  const reportCheckoutResult = useCallback(
    (
      orderBid: string,
      outcome: 'success' | 'failed' | 'cancelled',
      failureCategory?: CreatorBillingFailureCategory,
    ) => {
      const resultKey = `result:${orderBid || 'missing'}`;
      if (reportedAnalyticsKeysRef.current.has(resultKey)) {
        return;
      }
      reportedAnalyticsKeysRef.current.add(resultKey);
      trackCreatorBillingEventSafely(
        trackEvent,
        CREATOR_BILLING_ANALYTICS_EVENTS.result,
        buildCreatorBillingResultAnalytics({
          ...(orderBid ? { billOrderBid: orderBid } : {}),
          paymentProvider: 'stripe',
          sourceSurface: 'stripe_return',
          outcome,
          failureCategory,
        }),
      );
    },
    [trackEvent],
  );

  const reportCheckoutStatus = useCallback(
    (orderBid: string, status: 'pending' | 'confirmation_failed') => {
      const statusKey = `status:${orderBid}:${status}`;
      if (reportedAnalyticsKeysRef.current.has(statusKey)) {
        return;
      }
      reportedAnalyticsKeysRef.current.add(statusKey);
      trackCreatorBillingEventSafely(
        trackEvent,
        CREATOR_BILLING_ANALYTICS_EVENTS.status,
        buildCreatorBillingStatusAnalytics({
          billOrderBid: orderBid,
          paymentProvider: 'stripe',
          sourceSurface: 'stripe_return',
          status,
        }),
      );
    },
    [trackEvent],
  );

  const syncBillingOrder = useCallback(
    async (orderBid: string) => {
      if (!orderBid) {
        reportCheckoutResult('', 'failed', 'missing_order');
        setState({
          status: 'error',
          messageKey: 'module.billing.result.missingOrder',
        });
        return;
      }

      setState({
        status: 'loading',
        messageKey: 'module.billing.result.processing',
        billingOrderBid: orderBid,
      });

      try {
        const result = (await request.post(
          `/api/billing/orders/${orderBid}/sync`,
          {
            session_id: sessionId || undefined,
          },
        )) as BillingSyncResponse;

        if (result.status === 'pending') {
          reportCheckoutStatus(orderBid, 'pending');
          setState({
            status: 'pending',
            messageKey: 'module.billing.result.pending',
            billingOrderBid: orderBid,
          });
          return;
        }

        if (result.status === 'refunded') {
          reportCheckoutResult(orderBid, 'failed', 'payment_failed');
          setState({
            status: 'error',
            messageKey: 'module.billing.result.errorTitle',
            billingOrderBid: orderBid,
          });
          return;
        }

        if (result.status !== 'paid') {
          // Failed, canceled, and timed-out billing orders can still transition
          // to paid after a later provider sync. Keep those observations
          // non-terminal so a retry can report the one eventual result.
          reportCheckoutStatus(orderBid, 'confirmation_failed');
          setState({
            status: 'error',
            messageKey: 'module.billing.result.errorTitle',
            billingOrderBid: orderBid,
          });
          return;
        }

        reportCheckoutResult(orderBid, 'success');
        await refreshBillingPageCaches();

        setState({
          status: 'success',
          messageKey: 'module.billing.result.success',
          billingOrderBid: orderBid,
        });
      } catch (error: any) {
        reportCheckoutStatus('', 'confirmation_failed');
        setState({
          status: 'error',
          messageKey: error?.message
            ? undefined
            : 'module.billing.result.errorTitle',
          messageText: error?.message || undefined,
          billingOrderBid: orderBid,
        });
      }
    },
    [reportCheckoutResult, reportCheckoutStatus, sessionId],
  );

  useEffect(() => {
    if (canceled) {
      reportCheckoutResult('', 'cancelled');
      setState({
        status: 'error',
        messageKey: 'module.billing.result.errorTitle',
        ...(billingOrderBid ? { billingOrderBid } : {}),
      });
      syncAttemptedRef.current = null;
      return;
    }
    if (!billingOrderBid) {
      reportCheckoutResult('', 'failed', 'missing_order');
      setState({
        status: 'error',
        messageKey: 'module.billing.result.missingOrder',
      });
      syncAttemptedRef.current = null;
      return;
    }

    const syncKey = `${billingOrderBid}:${sessionId}`;
    if (syncAttemptedRef.current === syncKey) {
      return;
    }
    syncAttemptedRef.current = syncKey;
    void syncBillingOrder(billingOrderBid);
  }, [
    billingOrderBid,
    canceled,
    reportCheckoutResult,
    sessionId,
    syncBillingOrder,
  ]);

  const message = useMemo(() => {
    if (state.messageText) {
      return state.messageText;
    }
    if (!state.messageKey) {
      return '';
    }
    const translated = t(state.messageKey);
    return translated === state.messageKey ? '' : translated;
  }, [state.messageKey, state.messageText, t]);

  const heading = useMemo(() => {
    if (state.status === 'success') {
      return t('module.billing.result.successTitle');
    }
    if (state.status === 'pending') {
      return t('module.billing.result.pendingTitle');
    }
    if (state.status === 'error') {
      return t('module.billing.result.errorTitle');
    }
    return t('module.billing.result.processing');
  }, [state.status, t]);

  useEffect(() => {
    if (state.status !== 'success') {
      if (redirectTimerRef.current) {
        clearInterval(redirectTimerRef.current);
        redirectTimerRef.current = null;
      }
      return;
    }

    setRedirectCountdown(3);
    redirectTimerRef.current = setInterval(() => {
      setRedirectCountdown(prev => {
        if (prev <= 1) {
          if (redirectTimerRef.current) {
            clearInterval(redirectTimerRef.current);
            redirectTimerRef.current = null;
          }
          router.push('/admin/billing');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (redirectTimerRef.current) {
        clearInterval(redirectTimerRef.current);
        redirectTimerRef.current = null;
      }
    };
  }, [router, state.status]);

  return (
    <div className='mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-6 px-6 text-center'>
      <div className='space-y-3'>
        <h1 className='text-2xl font-semibold'>{heading}</h1>
        {message ? (
          <p className='text-base text-muted-foreground'>{message}</p>
        ) : null}
        {state.status === 'success' ? (
          <p className='text-sm text-muted-foreground'>
            {t('module.billing.result.countdown', {
              seconds: redirectCountdown,
            })}
          </p>
        ) : null}
      </div>
      <div className='flex w-full flex-col gap-3'>
        {(state.status === 'pending' || state.status === 'error') &&
        billingOrderBid ? (
          <Button
            className='w-full'
            onClick={() => void syncBillingOrder(billingOrderBid)}
          >
            {t('module.billing.result.retry')}
          </Button>
        ) : null}
        <Button
          variant={state.status === 'success' ? 'outline' : 'default'}
          className='w-full'
          onClick={() => router.push('/admin/billing')}
        >
          {t('module.billing.result.openBilling')}
        </Button>
      </div>
    </div>
  );
}
