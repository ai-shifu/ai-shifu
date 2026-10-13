'use client';

import { useEffect, useMemo, useState, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { useTranslation } from 'react-i18next';
import {
  getPaymentDetail,
  syncStripeCheckout,
  syncPaymentOrder,
  type PaymentDetailResponse,
} from '@/api/order';
import { consumeStripeCheckoutSession } from '@/lib/stripe-storage';
import { useTracking } from '@/hooks/useTracking';
import {
  buildLearnerPaymentResultAnalytics,
  buildLearnerPaymentStatusAnalytics,
  type LearnerPaymentFailureCategory,
} from '@/lib/paymentAnalytics';

interface PaymentResultState {
  status: 'loading' | 'success' | 'pending' | 'error';
  message: string;
  orderId?: string;
  analyticsOrderId?: string;
  analyticsEligible?: boolean;
  courseId?: string;
  failureCategory?: LearnerPaymentFailureCategory;
  analyticsOutcome?: 'cancelled';
}

export default function LearnerPaymentResult({
  legacyStripe = false,
}: {
  legacyStripe?: boolean;
}) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const [state, setState] = useState<PaymentResultState>({
    status: 'loading',
    message: '',
  });
  const detailRequestsRef = useRef(
    new Map<string, Promise<PaymentDetailResponse>>(),
  );
  const sessionOrdersRef = useRef(new Map<string, string>());
  const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [redirectCountdown, setRedirectCountdown] = useState(3);
  const analyticsStatusRef = useRef('');

  const sessionId = searchParams.get('session_id') || '';
  const providedOrderId = searchParams.get('order_id') || '';
  const canceled = searchParams.get('canceled') === '1';

  useEffect(() => {
    let orderId = providedOrderId;
    if (!orderId && sessionId) {
      orderId =
        sessionOrdersRef.current.get(sessionId) ||
        consumeStripeCheckoutSession(sessionId) ||
        '';
      if (orderId) sessionOrdersRef.current.set(sessionId, orderId);
    }

    if (!orderId) {
      setState({
        status: 'error',
        message: t('module.pay.stripeResultMissingOrder'),
        failureCategory: 'missing_order',
      });
      return;
    }

    let active = true;
    const requestKey = `${legacyStripe}:${orderId}:${sessionId}`;
    let detailRequest = detailRequestsRef.current.get(requestKey);
    if (!detailRequest) {
      detailRequest = (async () => {
        const detail = await getPaymentDetail({ orderId });
        if (
          (!legacyStripe || detail.payment_channel === 'stripe') &&
          detail.status !== 1 &&
          (sessionId || !legacyStripe)
        ) {
          return legacyStripe
            ? syncStripeCheckout({ orderId, sessionId })
            : syncPaymentOrder({ orderId });
        }
        return detail;
      })();
      detailRequestsRef.current.set(requestKey, detailRequest);
    }
    (async () => {
      try {
        const detail = await detailRequest;
        if (!active) return;
        if (
          (!legacyStripe || detail.payment_channel === 'stripe') &&
          detail.status === 1
        ) {
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
            analyticsEligible:
              !legacyStripe || detail.payment_channel === 'stripe',
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
          analyticsEligible:
            !legacyStripe || detail.payment_channel === 'stripe',
          courseId: detail.course_id,
        });
      } catch (error: any) {
        if (!active) return;
        setState({
          status: 'error',
          message: error?.message || t('module.pay.stripeError'),
          orderId,
          failureCategory: 'status_lookup_failed',
        });
      }
    })();
    return () => {
      active = false;
    };
  }, [providedOrderId, sessionId, canceled, t, legacyStripe]);

  useEffect(() => {
    if (state.status === 'loading' || state.analyticsEligible === false) return;
    const analyticsState = state.analyticsOutcome || state.status;
    const key = `${state.analyticsOrderId || 'missing'}:${analyticsState}`;
    if (analyticsStatusRef.current === key) return;
    analyticsStatusRef.current = key;

    const base = {
      shifuBid: state.courseId,
      orderId: state.analyticsOrderId,
      channel: legacyStripe ? ('stripe' as const) : ('other' as const),
      surface: legacyStripe
        ? ('stripe_return' as const)
        : ('payment_return' as const),
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
  }, [state, trackEvent, legacyStripe]);

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
