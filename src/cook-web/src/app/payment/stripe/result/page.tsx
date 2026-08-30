'use client';

import { useEffect, useMemo, useState, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { useTranslation } from 'react-i18next';
import { getPaymentDetail, syncStripeCheckout } from '@/c-api/order';
import { consumeStripeCheckoutSession } from '@/lib/stripe-storage';
import { useTracking } from '@/c-common/hooks/useTracking';
import {
  buildLearnerPaymentResultAnalytics,
  buildLearnerPaymentStatusAnalytics,
  type LearnerPaymentFailureCategory,
} from '@/lib/paymentAnalytics';

interface StripeResultState {
  status: 'loading' | 'success' | 'pending' | 'error';
  message: string;
  orderId?: string;
  analyticsOrderId?: string;
  courseId?: string;
  failureCategory?: LearnerPaymentFailureCategory;
  analyticsOutcome?: 'cancelled';
}

export default function StripeResultPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const [state, setState] = useState<StripeResultState>({
    status: 'loading',
    message: '',
  });
  const syncAttemptedRef = useRef(false);
  const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [redirectCountdown, setRedirectCountdown] = useState(3);
  const lastSyncedOrderRef = useRef<string | undefined>(undefined);
  const analyticsStatusRef = useRef('');

  useEffect(() => {
    const sessionId = searchParams.get('session_id') || '';
    const providedOrderId = searchParams.get('order_id') || '';
    const canceled = searchParams.get('canceled') === '1';

    let orderId = providedOrderId;
    if (!orderId && sessionId) {
      orderId = consumeStripeCheckoutSession(sessionId) || '';
    }

    if (!orderId) {
      setState({
        status: 'error',
        message: t('module.pay.stripeResultMissingOrder'),
        failureCategory: 'missing_order',
      });
      return;
    }

    (async () => {
      try {
        let detail = await getPaymentDetail({ orderId });
        if (
          detail.payment_channel === 'stripe' &&
          detail.status !== 1 &&
          sessionId
        ) {
          if (
            !syncAttemptedRef.current ||
            lastSyncedOrderRef.current !== orderId
          ) {
            syncAttemptedRef.current = true;
            lastSyncedOrderRef.current = orderId;
            detail = await syncStripeCheckout({ orderId, sessionId });
          }
        }
        if (detail.payment_channel === 'stripe' && detail.status === 1) {
          setState({
            status: 'success',
            message: t('module.pay.paySuccess'),
            orderId,
            analyticsOrderId: orderId,
            courseId: detail.course_id,
          });
          return;
        }
        if (canceled) {
          setState({
            status: 'pending',
            message: t('module.pay.stripeResultPending'),
            orderId,
            analyticsOrderId: orderId,
            courseId: detail.course_id,
            analyticsOutcome: 'cancelled',
          });
          return;
        }
        setState({
          status: 'pending',
          message: t('module.pay.stripeResultPending'),
          orderId,
          analyticsOrderId: orderId,
          courseId: detail.course_id,
        });
      } catch (error: any) {
        setState({
          status: 'error',
          message: error?.message || t('module.pay.stripeError'),
          orderId,
          failureCategory: 'status_lookup_failed',
        });
      }
    })();
  }, [searchParams, t]);

  useEffect(() => {
    if (state.status === 'loading') return;
    const analyticsState = state.analyticsOutcome || state.status;
    const key = `${state.analyticsOrderId || 'missing'}:${analyticsState}`;
    if (analyticsStatusRef.current === key) return;
    analyticsStatusRef.current = key;

    const base = {
      shifuBid: state.courseId,
      orderId: state.analyticsOrderId,
      channel: 'stripe' as const,
      surface: 'stripe_return' as const,
    };
    if (state.analyticsOutcome === 'cancelled') {
      trackEvent(
        'learner_payment_result',
        buildLearnerPaymentResultAnalytics({
          ...base,
          outcome: 'cancelled',
        }),
      );
      return;
    }
    if (state.status === 'pending') {
      trackEvent(
        'learner_payment_status',
        buildLearnerPaymentStatusAnalytics({ ...base, status: 'pending' }),
      );
      return;
    }
    trackEvent(
      'learner_payment_result',
      buildLearnerPaymentResultAnalytics({
        ...base,
        outcome: state.status === 'success' ? 'success' : 'failed',
        failureCategory: state.failureCategory,
      }),
    );
  }, [state, trackEvent]);

  useEffect(() => {
    syncAttemptedRef.current = false;
    lastSyncedOrderRef.current = undefined;
  }, [state.orderId]);

  const heading = useMemo(() => {
    if (state.status === 'success') {
      return t('module.pay.stripeResultSuccessTitle');
    }
    if (state.status === 'pending') {
      return t('module.pay.stripeResultPendingTitle');
    }
    if (state.status === 'error') {
      return t('module.pay.stripeResultErrorTitle');
    }
    return t('module.pay.processing');
  }, [state.status, t]);

  useEffect(() => {
    if (state.status !== 'success' || !state.courseId) {
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
          router.push(`/c/${state.courseId}`);
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
  }, [router, state.courseId, state.status]);

  return (
    <div className='mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-6 px-6 text-center'>
      <div className='space-y-3'>
        <h1 className='text-2xl font-semibold'>{heading}</h1>
        {state.message && (
          <p className='text-muted-foreground text-base'>{state.message}</p>
        )}
        {state.status === 'success' && state.courseId ? (
          <p className='text-sm text-muted-foreground'>
            {t('module.pay.stripeResultRedirectCountDown', {
              seconds: redirectCountdown,
            })}
          </p>
        ) : null}
      </div>
      <div className='flex flex-col gap-3 w-full'>
        <Button
          className='w-full'
          onClick={() =>
            router.push(state.courseId ? `/c/${state.courseId}` : '/c')
          }
        >
          {t('module.pay.stripeResultBackToChat')}
        </Button>
        <Button
          variant='outline'
          className='w-full'
          onClick={() => router.push('/')}
        >
          {t('module.pay.stripeResultHome')}
        </Button>
      </div>
    </div>
  );
}
