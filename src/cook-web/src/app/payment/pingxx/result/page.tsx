'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { useTranslation } from 'react-i18next';
import { queryOrder } from '@/c-api/order';
import { ORDER_STATUS } from '@/app/c/[[...id]]/Components/Pay/constans';

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 15;

interface PingxxResultState {
  status: 'loading' | 'success' | 'pending' | 'error';
  message: string;
  orderId?: string;
  courseId?: string;
  redirectPath?: string;
}

interface OrderSnapshot {
  course_id?: string;
  status: number;
}

const PINGXX_PENDING_STATUSES = new Set([
  ORDER_STATUS.BUY_STATUS_INIT,
  ORDER_STATUS.BUY_STATUS_TO_BE_PAID,
]);

const resolveRedirectPath = (
  redirectPath: string,
  courseId?: string,
): string => {
  if (
    redirectPath &&
    redirectPath.startsWith('/') &&
    !redirectPath.startsWith('//')
  ) {
    return redirectPath;
  }
  if (courseId) {
    return `/c/${courseId}`;
  }
  return '/c';
};

export default function PingxxResultPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const [state, setState] = useState<PingxxResultState>({
    status: 'loading',
    message: '',
  });
  const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pollAttemptsRef = useRef(0);
  const [redirectCountdown, setRedirectCountdown] = useState(3);

  useEffect(() => {
    const orderId = searchParams.get('order_id') || '';
    const providedCourseId = searchParams.get('course_id') || '';
    const redirectPath = searchParams.get('redirect') || '';

    if (!orderId) {
      setState({
        status: 'error',
        message: t('module.pay.stripeResultMissingOrder'),
      });
      return;
    }

    let cancelled = false;

    const checkOrderStatus = async () => {
      try {
        const result = (await queryOrder({ orderId })) as OrderSnapshot;
        if (cancelled) {
          return;
        }

        const courseId = result?.course_id || providedCourseId;
        if (result?.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
          setState({
            status: 'success',
            message: t('module.pay.paySuccess'),
            orderId,
            courseId,
            redirectPath: resolveRedirectPath(redirectPath, courseId),
          });
          return;
        }

        if (result?.status === ORDER_STATUS.BUY_STATUS_REFUND) {
          setState({
            status: 'error',
            message: t('module.order.paymentStatus.refunded'),
            orderId,
            courseId,
            redirectPath: resolveRedirectPath(redirectPath, courseId),
          });
          return;
        }

        if (!PINGXX_PENDING_STATUSES.has(result?.status)) {
          setState({
            status: 'error',
            message: t('module.pay.payFailed'),
            orderId,
            courseId,
            redirectPath: resolveRedirectPath(redirectPath, courseId),
          });
          return;
        }

        pollAttemptsRef.current += 1;
        setState({
          status: 'pending',
          message: t('module.pay.pingxxResultPending'),
          orderId,
          courseId,
          redirectPath: resolveRedirectPath(redirectPath, courseId),
        });

        if (pollAttemptsRef.current < MAX_POLL_ATTEMPTS) {
          pollTimerRef.current = setTimeout(checkOrderStatus, POLL_INTERVAL_MS);
          return;
        }

        setState({
          status: 'error',
          message: t('module.pay.pingxxResultTimeout'),
          orderId,
          courseId,
          redirectPath: resolveRedirectPath(redirectPath, courseId),
        });
      } catch (error: any) {
        if (cancelled) {
          return;
        }
        setState({
          status: 'error',
          message: error?.message || t('module.pay.payFailed'),
          orderId,
          courseId: providedCourseId,
          redirectPath: resolveRedirectPath(redirectPath, providedCourseId),
        });
      }
    };

    pollAttemptsRef.current = 0;
    checkOrderStatus();

    return () => {
      cancelled = true;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [searchParams, t]);

  const redirectTarget = useMemo(
    () => resolveRedirectPath(state.redirectPath || '', state.courseId),
    [state.courseId, state.redirectPath],
  );

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
          router.push(redirectTarget);
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
  }, [redirectTarget, router, state.status]);

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

  return (
    <div className='mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-6 px-6 text-center'>
      <div className='space-y-3'>
        <h1 className='text-2xl font-semibold'>{heading}</h1>
        {state.message ? (
          <p className='text-base text-muted-foreground'>{state.message}</p>
        ) : null}
        {state.status === 'success' ? (
          <p className='text-sm text-muted-foreground'>
            {t('module.pay.stripeResultRedirectCountDown', {
              seconds: redirectCountdown,
            })}
          </p>
        ) : null}
      </div>
      <div className='flex w-full flex-col gap-3'>
        <Button
          className='w-full'
          onClick={() => router.push(redirectTarget)}
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
