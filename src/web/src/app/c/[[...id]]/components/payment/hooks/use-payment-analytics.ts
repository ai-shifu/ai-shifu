import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { PaymentChannel } from '@/api/order';
import type { toast as toastFn } from '@/hooks/use-toast';
import { useTracking } from '@/hooks/use-tracking';
import { getCurrencyCode } from '@/lib/currency';
import { resolveLearnerPaymentToast } from '@/lib/learner-error';
import {
  buildLearnerPaymentAttemptAnalytics,
  buildLearnerPaymentResultAnalytics,
  buildLearnerPaymentStatusAnalytics,
  isSupersededLearnerPaymentAttempt,
  normalizeLearnerPaymentChannel,
  normalizeLearnerPaymentCurrency,
  rememberLearnerProviderConfirmedChannel,
  resolveCurrentLearnerPaymentAttemptChannel,
  resolveLearnerPaymentAttributionChannel,
  resolveLearnerProviderConfirmedChannel,
  trackLearnerPaymentEventSafely,
  type LearnerPaymentAttemptContext,
  type LearnerPaymentChannel,
  type LearnerPaymentSurface,
} from '@/lib/payment-analytics';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import { PAY_CHANNEL_STRIPE } from '../payment-constants';

export type PaymentModalSurface = Extract<
  LearnerPaymentSurface,
  'desktop' | 'mobile'
>;

export type PaymentModalDismissSurface = 'modal' | 'payment_page';

type PaymentResultOutcome = 'success' | 'failed' | 'cancelled';

type PaymentToast = typeof toastFn;

interface UsePaymentAnalyticsOptions {
  courseId: string;
  surface: PaymentModalSurface;
}

/**
 * Attempt attribution and payment event producers shared by the desktop
 * PayModal and the MobilePaymentDialog. Call it before `usePaymentFlow` so
 * `trackPaymentResult` can be used from the `onOrderPaid` callback.
 */
export const usePaymentAnalytics = ({
  courseId,
  surface,
}: UsePaymentAnalyticsOptions) => {
  const { trackEvent } = useTracking();
  const paymentOrderIdRef = useRef('');
  const paymentAnalyticsLifecycleRef = useRef(0);
  const paymentAttemptSequenceRef = useRef(0);
  const paymentAttemptChannelsRef = useRef(new Set<LearnerPaymentChannel>());
  const activePaymentAttemptIdsRef = useRef(
    new Map<LearnerPaymentChannel, number>(),
  );
  const providerConfirmedChannelsByOrderRef = useRef(
    new Map<string, Set<LearnerPaymentChannel>>(),
  );
  const hadPaymentAttemptRef = useRef(false);
  const qrAttemptKeyRef = useRef('');

  const trackPaymentAttempt = useCallback(
    (rawChannel: string): LearnerPaymentAttemptContext | undefined => {
      try {
        const channel = normalizeLearnerPaymentChannel(rawChannel);
        const attemptId = ++paymentAttemptSequenceRef.current;
        paymentAttemptChannelsRef.current.add(channel);
        activePaymentAttemptIdsRef.current.set(channel, attemptId);
        const existingProviderEvidence =
          providerConfirmedChannelsByOrderRef.current.get(
            paymentOrderIdRef.current,
          );
        existingProviderEvidence?.delete(channel);
        if (existingProviderEvidence?.size === 0) {
          providerConfirmedChannelsByOrderRef.current.delete(
            paymentOrderIdRef.current,
          );
        }
        hadPaymentAttemptRef.current = true;
        trackLearnerPaymentEventSafely(
          trackEvent,
          'learner_payment_attempt',
          buildLearnerPaymentAttemptAnalytics({
            shifuBid: courseId,
            orderId: paymentOrderIdRef.current,
            channel,
            surface,
          }),
        );
        return {
          orderId: paymentOrderIdRef.current,
          lifecycle: paymentAnalyticsLifecycleRef.current,
          channel,
          attemptId,
        };
      } catch {
        return undefined;
      }
    },
    [courseId, surface, trackEvent],
  );

  const rememberProviderConfirmedChannel = useCallback(
    (attempt: LearnerPaymentAttemptContext | undefined) => {
      try {
        return rememberLearnerProviderConfirmedChannel(
          providerConfirmedChannelsByOrderRef.current,
          attempt,
          paymentOrderIdRef.current,
          paymentAnalyticsLifecycleRef.current,
          paymentAttemptChannelsRef.current,
          activePaymentAttemptIdsRef.current,
        );
      } catch {
        return false;
      }
    },
    [],
  );

  const resolveCurrentPaymentAttemptChannel = useCallback(
    (attempt: LearnerPaymentAttemptContext | undefined) =>
      resolveCurrentLearnerPaymentAttemptChannel(
        attempt,
        paymentOrderIdRef.current,
        paymentAnalyticsLifecycleRef.current,
        paymentAttemptChannelsRef.current,
        activePaymentAttemptIdsRef.current,
      ),
    [],
  );

  const trackPaymentResult = useCallback(
    (
      outcome: PaymentResultOutcome,
      failureCategory?: 'provider_failed',
      confirmedAttempt?: LearnerPaymentAttemptContext,
    ) => {
      try {
        const currentOrderId = paymentOrderIdRef.current;
        const providerConfirmedChannels =
          providerConfirmedChannelsByOrderRef.current.get(currentOrderId) || [];
        const confirmedChannel = confirmedAttempt
          ? resolveCurrentPaymentAttemptChannel(confirmedAttempt)
          : outcome === 'success'
            ? resolveLearnerProviderConfirmedChannel(
                providerConfirmedChannels,
                paymentAttemptChannelsRef.current,
              )
            : undefined;
        const usesSupersededAttemptFallback =
          outcome === 'success' &&
          !confirmedChannel &&
          isSupersededLearnerPaymentAttempt(
            confirmedAttempt,
            currentOrderId,
            paymentAnalyticsLifecycleRef.current,
            paymentAttemptChannelsRef.current,
            activePaymentAttemptIdsRef.current,
          );
        if (
          confirmedAttempt &&
          !confirmedChannel &&
          !usesSupersededAttemptFallback
        ) {
          return;
        }
        const channel = resolveLearnerPaymentAttributionChannel(
          paymentAttemptChannelsRef.current,
          confirmedChannel,
        );
        if (!channel) {
          if (outcome === 'success' && !confirmedAttempt) {
            providerConfirmedChannelsByOrderRef.current.delete(currentOrderId);
          }
          return;
        }
        if (confirmedChannel) {
          paymentAttemptChannelsRef.current.delete(confirmedChannel);
          activePaymentAttemptIdsRef.current.delete(confirmedChannel);
        } else {
          paymentAttemptChannelsRef.current.clear();
          activePaymentAttemptIdsRef.current.clear();
        }
        if (outcome === 'success' || !confirmedChannel) {
          providerConfirmedChannelsByOrderRef.current.delete(currentOrderId);
        } else {
          const remainingConfirmedChannels =
            providerConfirmedChannelsByOrderRef.current.get(currentOrderId);
          remainingConfirmedChannels?.delete(confirmedChannel);
          if (remainingConfirmedChannels?.size === 0) {
            providerConfirmedChannelsByOrderRef.current.delete(currentOrderId);
          }
        }
        trackLearnerPaymentEventSafely(
          trackEvent,
          'learner_payment_result',
          buildLearnerPaymentResultAnalytics({
            shifuBid: courseId,
            orderId: paymentOrderIdRef.current,
            channel,
            surface,
            outcome,
            failureCategory,
          }),
        );
      } catch {}
    },
    [courseId, resolveCurrentPaymentAttemptChannel, surface, trackEvent],
  );

  const trackPaymentPending = useCallback(
    (attempt?: LearnerPaymentAttemptContext) => {
      try {
        const confirmedChannel = attempt
          ? resolveCurrentPaymentAttemptChannel(attempt)
          : undefined;
        if (attempt && !confirmedChannel) return;
        const channel = resolveLearnerPaymentAttributionChannel(
          paymentAttemptChannelsRef.current,
          confirmedChannel,
        );
        if (!channel) return;
        trackLearnerPaymentEventSafely(
          trackEvent,
          'learner_payment_status',
          buildLearnerPaymentStatusAnalytics({
            shifuBid: courseId,
            orderId: paymentOrderIdRef.current,
            channel,
            surface,
            status: 'pending',
          }),
        );
      } catch {}
    },
    [courseId, resolveCurrentPaymentAttemptChannel, surface, trackEvent],
  );

  /**
   * Tracks a QR attempt once per order, channel and QR URL. Only the desktop
   * cashier renders QR codes; the mobile dialog opens the provider URL instead.
   */
  const trackQrPaymentAttempt = useCallback(
    (rawChannel: string, nextOrderId: string, qrUrl: string) => {
      const attemptKey = `${nextOrderId}:${rawChannel}:${qrUrl}`;
      if (qrAttemptKeyRef.current === attemptKey) return;
      qrAttemptKeyRef.current = attemptKey;
      trackPaymentAttempt(rawChannel);
    },
    [trackPaymentAttempt],
  );

  const trackCouponApplied = useCallback(() => {
    trackLearnerPaymentEventSafely(trackEvent, 'learner_coupon_apply', {
      shifu_bid: courseId,
      outcome: 'success',
    });
  }, [courseId, trackEvent]);

  /** Drops attempt attribution so a new order or modal lifecycle starts clean. */
  const resetAttemptAttribution = useCallback(() => {
    paymentAnalyticsLifecycleRef.current += 1;
    paymentAttemptChannelsRef.current.clear();
    activePaymentAttemptIdsRef.current.clear();
    providerConfirmedChannelsByOrderRef.current.clear();
    hadPaymentAttemptRef.current = false;
  }, []);

  return {
    courseId,
    trackEvent,
    paymentOrderIdRef,
    hadPaymentAttemptRef,
    qrAttemptKeyRef,
    trackPaymentAttempt,
    trackQrPaymentAttempt,
    rememberProviderConfirmedChannel,
    trackPaymentResult,
    trackPaymentPending,
    trackCouponApplied,
    resetAttemptAttribution,
  };
};

export type PaymentAnalytics = ReturnType<typeof usePaymentAnalytics>;

interface UsePaymentAnalyticsLifecycleOptions {
  open: boolean;
  ready: boolean;
  orderId: string;
  isTimeout: boolean;
  displayPrice: string;
  currencySymbol: string;
}

/**
 * Order, timeout and modal-visibility effects for the payment analytics.
 * Call it after `usePaymentFlow` once the display price and readiness are
 * known. Effects run in this order: order sync, unmount reset, timeout
 * pending status, modal view.
 */
export const usePaymentAnalyticsLifecycle = (
  analytics: PaymentAnalytics,
  {
    open,
    ready,
    orderId,
    isTimeout,
    displayPrice,
    currencySymbol,
  }: UsePaymentAnalyticsLifecycleOptions,
) => {
  const {
    courseId,
    trackEvent,
    paymentOrderIdRef,
    hadPaymentAttemptRef,
    qrAttemptKeyRef,
    trackPaymentPending,
    resetAttemptAttribution,
  } = analytics;
  const timeoutAnalyticsReportedRef = useRef(false);
  const modalViewTrackedRef = useRef(false);

  useEffect(() => {
    if (paymentOrderIdRef.current !== orderId) {
      resetAttemptAttribution();
    }
    paymentOrderIdRef.current = orderId;
  }, [orderId, paymentOrderIdRef, resetAttemptAttribution]);

  useEffect(
    () => () => {
      resetAttemptAttribution();
    },
    [resetAttemptAttribution],
  );

  useEffect(() => {
    if (!isTimeout) {
      timeoutAnalyticsReportedRef.current = false;
      return;
    }
    if (timeoutAnalyticsReportedRef.current) return;
    timeoutAnalyticsReportedRef.current = true;
    trackPaymentPending();
  }, [isTimeout, trackPaymentPending]);

  const currencyCode = useMemo(
    () => normalizeLearnerPaymentCurrency(getCurrencyCode(currencySymbol)),
    [currencySymbol],
  );

  useEffect(() => {
    if (!open) {
      modalViewTrackedRef.current = false;
      resetAttemptAttribution();
      qrAttemptKeyRef.current = '';
      return;
    }
    if (!ready) {
      return;
    }
    if (modalViewTrackedRef.current) {
      return;
    }
    modalViewTrackedRef.current = true;
    trackLearnerPaymentEventSafely(trackEvent, 'learner_pay_modal_view', {
      shifu_bid: courseId,
      price_amount: Number.isFinite(Number(displayPrice))
        ? Number(displayPrice)
        : 0,
      currency: currencyCode,
    });
  }, [
    courseId,
    currencyCode,
    displayPrice,
    open,
    qrAttemptKeyRef,
    ready,
    resetAttemptAttribution,
    trackEvent,
  ]);

  const trackModalDismiss = useCallback(
    (dismissSurface: PaymentModalDismissSurface = 'modal') => {
      const hadPaymentAttempt = hadPaymentAttemptRef.current;
      trackLearnerPaymentEventSafely(trackEvent, 'learner_pay_modal_dismiss', {
        shifu_bid: courseId,
        ...(orderId ? { order_id: orderId } : {}),
        dismiss_surface: dismissSurface,
        had_payment_attempt: hadPaymentAttempt,
      });
    },
    [courseId, hadPaymentAttemptRef, orderId, trackEvent],
  );

  return { trackModalDismiss };
};

interface UsePaymentOutcomeHandlersOptions {
  orderId: string;
  stripeCheckoutUrl: string;
  stripeCheckoutSessionId?: string;
  syncOrderStatus: (params?: {
    paymentChannel?: PaymentChannel;
  }) => Promise<unknown>;
  toast: PaymentToast;
}

interface SettleWechatJsapiPaymentParams {
  attempt: LearnerPaymentAttemptContext | undefined;
  /** Invokes the provider; resolves when WeChat reports a successful payment. */
  pay: () => Promise<unknown>;
  syncParams: { paymentChannel?: PaymentChannel };
  /** Optional hook for surface-specific logging before the failure toast. */
  onPayError?: (error: unknown) => void;
}

/**
 * Stripe and WeChat JSAPI result handling shared by both payment surfaces:
 * provider confirmation, order sync, toasts and result/pending analytics.
 */
export const usePaymentOutcomeHandlers = (
  analytics: PaymentAnalytics,
  {
    orderId,
    stripeCheckoutUrl,
    stripeCheckoutSessionId,
    syncOrderStatus,
    toast,
  }: UsePaymentOutcomeHandlersOptions,
) => {
  const { t } = useTranslation();
  const {
    trackPaymentAttempt,
    rememberProviderConfirmedChannel,
    trackPaymentPending,
    trackPaymentResult,
  } = analytics;

  const handleStripeSuccess = useCallback(
    async (attempt?: LearnerPaymentAttemptContext) => {
      try {
        rememberProviderConfirmedChannel(attempt);
        await syncOrderStatus();
        toast({ title: t('module.pay.paySuccess') });
      } catch {
        trackPaymentPending(attempt);
        toast({
          title: t('module.pay.paymentStatusSyncPending'),
          variant: 'default',
        });
      }
    },
    [
      rememberProviderConfirmedChannel,
      syncOrderStatus,
      t,
      toast,
      trackPaymentPending,
    ],
  );

  const handleStripeCheckout = useCallback(() => {
    if (stripeCheckoutUrl) {
      trackPaymentAttempt(PAY_CHANNEL_STRIPE);
      if (stripeCheckoutSessionId && orderId) {
        rememberStripeCheckoutSession(stripeCheckoutSessionId, orderId);
      }
      window.location.href = stripeCheckoutUrl;
    }
  }, [
    orderId,
    stripeCheckoutSessionId,
    stripeCheckoutUrl,
    trackPaymentAttempt,
  ]);

  const handleStripeError = useCallback(
    (
      message: string,
      status: 'failed' | 'pending',
      attempt?: LearnerPaymentAttemptContext,
    ) => {
      const resolvedToast = resolveLearnerPaymentToast({
        message,
        fallbackMessage: t('module.pay.payFailed'),
        canceledMessage: t('module.pay.paymentCanceled'),
        unsupportedMessage: t('module.pay.wechatJsapiUnavailable'),
      });
      if (status === 'pending') {
        trackPaymentPending(attempt);
      } else {
        trackPaymentResult(
          resolvedToast.variant === 'default' ? 'cancelled' : 'failed',
          resolvedToast.variant === 'default' ? undefined : 'provider_failed',
          attempt,
        );
      }
      toast({
        title: resolvedToast.message,
        variant: resolvedToast.variant,
      });
    },
    [t, toast, trackPaymentPending, trackPaymentResult],
  );

  const handleStripeConfirmationUnavailable = useCallback(
    (attempt: LearnerPaymentAttemptContext) => {
      trackPaymentPending(attempt);
    },
    [trackPaymentPending],
  );

  const settleWechatJsapiPayment = useCallback(
    async ({
      attempt,
      pay,
      syncParams,
      onPayError,
    }: SettleWechatJsapiPaymentParams) => {
      try {
        await pay();
        rememberProviderConfirmedChannel(attempt);
        try {
          await syncOrderStatus(syncParams);
        } catch {
          trackPaymentPending(attempt);
          toast({
            title: t('module.pay.paymentStatusSyncPending'),
            variant: 'default',
          });
          return;
        }
        toast({ title: t('module.pay.paySuccess') });
      } catch (error) {
        onPayError?.(error);
        const resolvedToast = resolveLearnerPaymentToast({
          error: error as Error,
          fallbackMessage: t('module.pay.payFailed'),
          canceledMessage: t('module.pay.paymentCanceled'),
          unsupportedMessage: t('module.pay.wechatJsapiUnavailable'),
        });
        toast({
          title: resolvedToast.message,
          variant: resolvedToast.variant,
        });
        trackPaymentResult(
          resolvedToast.variant === 'default' ? 'cancelled' : 'failed',
          resolvedToast.variant === 'default' ? undefined : 'provider_failed',
          attempt,
        );
      }
    },
    [
      rememberProviderConfirmedChannel,
      syncOrderStatus,
      t,
      toast,
      trackPaymentPending,
      trackPaymentResult,
    ],
  );

  return {
    handleStripeSuccess,
    handleStripeCheckout,
    handleStripeError,
    handleStripeConfirmationUnavailable,
    settleWechatJsapiPayment,
  };
};
