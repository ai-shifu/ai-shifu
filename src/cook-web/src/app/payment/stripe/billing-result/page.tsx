'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import request from '@/lib/request';
import { consumeStripeCheckoutSession } from '@/lib/stripe-storage';
import { useTranslation } from 'react-i18next';

type BillingResultStatus = 'loading' | 'success' | 'pending' | 'error';

type BillingSyncResponse = {
  status?: string;
};

type StripeBillingResultState = {
  status: BillingResultStatus;
  message: string;
  billingOrderBid?: string;
};

export default function StripeBillingResultPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { t } = useTranslation();
  const [state, setState] = useState<StripeBillingResultState>({
    status: 'loading',
    message: '',
  });
  const [redirectCountdown, setRedirectCountdown] = useState(3);
  const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const syncAttemptedRef = useRef<string | null>(null);
  const providedBillingOrderBid = searchParams.get('bill_order_bid') || '';
  const sessionId = searchParams.get('session_id') || '';
  const missingOrderMessage = t('module.billing.result.missingOrder');
  const processingMessage = t('module.billing.result.processing');
  const pendingMessage = t('module.billing.result.pending');
  const successMessage = t('module.billing.result.success');
  const errorTitle = t('module.billing.result.errorTitle');

  const billingOrderBid = useMemo(() => {
    if (providedBillingOrderBid) {
      return providedBillingOrderBid;
    }
    if (!sessionId) {
      return '';
    }
    return consumeStripeCheckoutSession(sessionId) || '';
  }, [providedBillingOrderBid, sessionId]);

  const syncBillingOrder = useCallback(
    async (orderBid: string) => {
      if (!orderBid) {
        setState({
          status: 'error',
          message: missingOrderMessage,
        });
        return;
      }

      setState({
        status: 'loading',
        message: processingMessage,
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
          setState({
            status: 'pending',
            message: pendingMessage,
            billingOrderBid: orderBid,
          });
          return;
        }

        setState({
          status: 'success',
          message: successMessage,
          billingOrderBid: orderBid,
        });
      } catch (error: any) {
        setState({
          status: 'error',
          message: error?.message || errorTitle,
          billingOrderBid: orderBid,
        });
      }
    },
    [
      errorTitle,
      missingOrderMessage,
      pendingMessage,
      processingMessage,
      sessionId,
      successMessage,
    ],
  );

  useEffect(() => {
    if (!billingOrderBid) {
      setState({
        status: 'error',
        message: missingOrderMessage,
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
  }, [billingOrderBid, missingOrderMessage, sessionId, syncBillingOrder]);

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
        {state.message ? (
          <p className='text-base text-muted-foreground'>{state.message}</p>
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
