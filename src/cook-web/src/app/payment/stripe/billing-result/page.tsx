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

type StripeBillingResultMessageKey =
  | 'module.billing.result.missingOrder'
  | 'module.billing.result.processing'
  | 'module.billing.result.pending'
  | 'module.billing.result.success'
  | 'module.billing.result.errorTitle';

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
  const [state, setState] = useState<StripeBillingResultState>({
    status: 'loading',
    messageKey: 'module.billing.result.processing',
  });
  const [redirectCountdown, setRedirectCountdown] = useState(3);
  const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const syncAttemptedRef = useRef<string | null>(null);
  const providedBillingOrderBid = searchParams.get('bill_order_bid') || '';
  const sessionId = searchParams.get('session_id') || '';

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
          setState({
            status: 'pending',
            messageKey: 'module.billing.result.pending',
            billingOrderBid: orderBid,
          });
          return;
        }

        setState({
          status: 'success',
          messageKey: 'module.billing.result.success',
          billingOrderBid: orderBid,
        });
      } catch (error: any) {
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
    [sessionId],
  );

  useEffect(() => {
    if (!billingOrderBid) {
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
  }, [billingOrderBid, sessionId, syncBillingOrder]);

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

  useEffect(() => {
    if (state.status === 'success' && redirectCountdown === 0) {
      router.push('/admin/billing');
    }
  }, [redirectCountdown, router, state.status]);

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
