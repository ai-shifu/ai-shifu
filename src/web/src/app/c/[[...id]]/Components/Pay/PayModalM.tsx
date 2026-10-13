import { usePaymentActionUnavailableTracking } from '@/hooks/usePaymentActionUnavailableTracking';
import {
  hasPaymentMethod,
  resolvePaymentOption,
  defaultPaymentSelection,
  resolvePaymentAction,
  canOpenPaymentQr,
  paymentSelectionKey,
  hostedPaymentOptions,
  resolvePaymentPresentation,
  resolveJsapiParams,
  resolveRequestedPaymentProvider,
} from '@/lib/paymentContracts';
import styles from './PayModalM.module.scss';

import { memo, useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { cn } from '@/lib/utils';

import Image from 'next/image';
import weixinIcon from '@/assets/newchat/weixin.png';
import zhifuboIcon from '@/assets/newchat/zhifubao.png';
import paySuccessBg from '@/assets/newchat/pay-success@2x.png';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { RadioGroup, RadioGroupItem } from '@/components/ui/RadioGroup';

import {
  PAY_CHANNEL_WECHAT,
  PAY_CHANNEL_WECHAT_JSAPI,
  PAY_CHANNEL_ZHIFUBAO,
  PAY_CHANNEL_STRIPE,
} from './constans';
import { isWechatJsapiAvailable } from './wechatJsapi';
import MainButtonM from '@/components/m/MainButtonM';
import PaymentSdkForm, { hasPaymentSdkHandler } from './PaymentSdkForm';

import { usePaymentFlow } from './hooks/usePaymentFlow';
import { useWechat } from '@/hooks/useWechat';

import { toast } from '@/hooks/useToast';
import { resolveLearnerPaymentToast } from '@/lib/learnerError';
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
} from '@/lib/paymentAnalytics';

import { inWechat } from '@/constants/uiConstants';
import { useDisclosure } from '@/hooks/useDisclosure';
import { SettingInputM } from '@/components/m/SettingInputM';
import PayModalFooter from './PayModalFooter';

import { getStringEnv } from '@/lib/envUtils';
import { useUserStore } from '@/store';
import { shifu } from '@/lib/shifu/Shifu';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';
import type { NativePaymentPayload, PaymentChannel } from '@/api/order';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import { getCourseInfo } from '@/api/course';
import { useTracking } from '@/hooks/useTracking';
import { getCurrencyCode } from '@/lib/currency';
const CompletedSection = memo(() => {
  const { t } = useTranslation();
  return (
    <div className={styles.completedSection}>
      <div className={styles.title}>{t('module.pay.paySuccess')}</div>
      <div className={styles.completeWrapper}>
        <Image
          className={styles.paySuccessBg}
          src={paySuccessBg.src}
          alt='pay-success-bg'
        />
      </div>
      <PayModalFooter className={styles.payModalFooter} />
    </div>
  );
});

CompletedSection.displayName = 'CompletedSection';

const defaultMobileChannel = inWechat()
  ? PAY_CHANNEL_WECHAT_JSAPI
  : PAY_CHANNEL_ZHIFUBAO;

export const PayModalM = ({
  open = false,
  onCancel,
  onOk,
  type = '',
  payload = {},
}) => {
  const [payChannel, setPayChannel] = useState(defaultMobileChannel);
  const [couponCodeInput, setCouponCodeInput] = useState('');
  const [previewPrice, setPreviewPrice] = useState('0');
  const [previewInitLoading, setPreviewInitLoading] = useState(true);
  const modalViewTrackedRef = useRef(false);
  const skipNextCancelEventRef = useRef(false);

  const courseId = getStringEnv('courseId');
  const { isLoggedIn, userInfo } = useUserStore(
    useShallow(state => ({
      isLoggedIn: state.isLoggedIn,
      userInfo: state.userInfo,
    })),
  );
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const { payByJsApi } = useWechat();
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
  const timeoutAnalyticsReportedRef = useRef(false);

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
            surface: 'mobile',
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
    [courseId, trackEvent],
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
      outcome: 'success' | 'failed' | 'cancelled',
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
            surface: 'mobile',
            outcome,
            failureCategory,
          }),
        );
      } catch {}
    },
    [courseId, resolveCurrentPaymentAttemptChannel, trackEvent],
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
            surface: 'mobile',
            status: 'pending',
          }),
        );
      } catch {}
    },
    [courseId, resolveCurrentPaymentAttemptChannel, trackEvent],
  );
  const {
    open: couponCodeModalOpen,
    onClose: onCouponCodeModalClose,
    onOpen: onCouponCodeModalOpen,
  } = useDisclosure();
  const { previewMode } = useSystemStore(
    useShallow(state => ({ previewMode: state.previewMode })),
  );

  const {
    orderId,
    price,
    originalPrice,
    priceItems,
    couponCode: appliedCouponCode,
    paymentInfo,
    paymentOptions,
    isLoading,
    initLoading: hookInitLoading,
    isCompleted,
    isTimeout,
    initializeOrder,
    refreshPayment,
    applyCoupon,
    syncOrderStatus,
  } = usePaymentFlow({
    type,
    payload,
    courseId,
    isLoggedIn,
    onOrderPaid: () => {
      trackPaymentResult('success');
      onOk?.();
    },
  });

  useEffect(() => {
    if (paymentOrderIdRef.current !== orderId) {
      paymentAnalyticsLifecycleRef.current += 1;
      paymentAttemptChannelsRef.current.clear();
      activePaymentAttemptIdsRef.current.clear();
      providerConfirmedChannelsByOrderRef.current.clear();
      hadPaymentAttemptRef.current = false;
    }
    paymentOrderIdRef.current = orderId;
  }, [orderId]);

  useEffect(
    () => () => {
      paymentAnalyticsLifecycleRef.current += 1;
      paymentAttemptChannelsRef.current.clear();
      activePaymentAttemptIdsRef.current.clear();
      providerConfirmedChannelsByOrderRef.current.clear();
      hadPaymentAttemptRef.current = false;
    },
    [],
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

  const displayPrice = isLoggedIn ? price : previewPrice;
  const displayOriginalPrice = isLoggedIn ? originalPrice : previewPrice;
  const ready = isLoggedIn ? !hookInitLoading : !previewInitLoading;
  const {
    stripePublishableKey,
    stripeEnabled,
    paymentChannels,
    currencySymbol,
    enableWxcode,
  } = useEnvStore(
    useShallow(state => ({
      stripePublishableKey: state.stripePublishableKey,
      stripeEnabled: state.stripeEnabled,
      paymentChannels: state.paymentChannels,
      currencySymbol: state.currencySymbol || '¥',
      enableWxcode: state.enableWxcode,
    })),
  );
  const initialPaymentRequestedRef = useRef(false);
  const currencyCode = useMemo(
    () => normalizeLearnerPaymentCurrency(getCurrencyCode(currencySymbol)),
    [currencySymbol],
  );
  const trackModalDismiss = useCallback(() => {
    const hadPaymentAttempt = hadPaymentAttemptRef.current;
    trackLearnerPaymentEventSafely(trackEvent, 'learner_pay_modal_dismiss', {
      shifu_bid: courseId,
      ...(orderId ? { order_id: orderId } : {}),
      dismiss_surface: 'modal',
      had_payment_attempt: hadPaymentAttempt,
    });
  }, [courseId, orderId, trackEvent]);

  useEffect(() => {
    if (!open) {
      modalViewTrackedRef.current = false;
      paymentAnalyticsLifecycleRef.current += 1;
      paymentAttemptChannelsRef.current.clear();
      activePaymentAttemptIdsRef.current.clear();
      providerConfirmedChannelsByOrderRef.current.clear();
      hadPaymentAttemptRef.current = false;
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
  }, [courseId, currencyCode, displayPrice, open, ready, trackEvent]);
  const normalizedPaymentChannels = useMemo(
    () => (paymentChannels || []).map(channel => channel.trim().toLowerCase()),
    [paymentChannels],
  );
  const pingxxChannelEnabled = normalizedPaymentChannels.includes('pingxx');
  const alipayChannelEnabled = normalizedPaymentChannels.includes('alipay');
  const wechatpayChannelEnabled =
    normalizedPaymentChannels.includes('wechatpay');
  const stripeChannelEnabled = normalizedPaymentChannels.includes('stripe');
  const isStripeAvailable = paymentOptions
    ? hostedPaymentOptions(paymentOptions).length > 0
    : stripeChannelEnabled &&
      stripeEnabled === 'true' &&
      Boolean(stripePublishableKey);
  const isWechatBrowser = useMemo(
    () => typeof navigator !== 'undefined' && inWechat(),
    [],
  );
  const wechatJsapiAvailable = isWechatJsapiAvailable({
    inWechatBrowser: isWechatBrowser,
    enableWxcode,
    openId: userInfo?.openid,
  });
  const wechatPaymentAvailable = paymentOptions
    ? hasPaymentMethod(paymentOptions, 'wechat')
    : pingxxChannelEnabled || wechatpayChannelEnabled;
  const alipayPaymentAvailable = paymentOptions
    ? hasPaymentMethod(paymentOptions, 'alipay')
    : pingxxChannelEnabled || alipayChannelEnabled;
  const qrChannelEnabled = paymentOptions
    ? paymentOptions.some(
        option => option.action === 'qr' || option.action === 'jsapi',
      )
    : wechatPaymentAvailable || alipayPaymentAvailable;
  const selectedOption = resolvePaymentOption(paymentOptions, payChannel);
  const wechatRowOption =
    selectedOption?.method === 'wechat'
      ? selectedOption
      : paymentOptions?.find(
          item =>
            item.method === 'wechat' &&
            item.action === 'jsapi' &&
            wechatJsapiAvailable,
        ) ||
        paymentOptions?.find(
          item => item.method === 'wechat' && item.action === 'qr',
        ) ||
        paymentOptions?.find(item => item.method === 'wechat');
  const alipayRowOption =
    selectedOption?.method === 'alipay'
      ? selectedOption
      : paymentOptions?.find(item => item.method === 'alipay');
  const wechatSelectionKey =
    wechatRowOption && paymentOptions
      ? paymentSelectionKey(wechatRowOption, paymentOptions)
      : PAY_CHANNEL_WECHAT_JSAPI;
  const alipaySelectionKey =
    alipayRowOption && paymentOptions
      ? paymentSelectionKey(alipayRowOption, paymentOptions)
      : PAY_CHANNEL_ZHIFUBAO;
  const radioSelectionKey =
    selectedOption && paymentOptions
      ? paymentSelectionKey(selectedOption, paymentOptions)
      : payChannel;
  const hostedOptions = hostedPaymentOptions(paymentOptions);
  const isHostedPaymentSelected = selectedOption
    ? ['redirect', 'sdk_confirm'].includes(selectedOption.action) &&
      !['wechat', 'alipay'].includes(selectedOption.method)
    : payChannel.startsWith('stripe');
  const hostedProvider =
    paymentInfo.paymentChannel || selectedOption?.provider || 'stripe';
  const [presentedQr, setPresentedQr] = useState<{
    orderId: string;
    selection: string;
    url: string;
  } | null>(null);
  const hostedAttemptChannel =
    hostedProvider === 'stripe' ? PAY_CHANNEL_STRIPE : 'other';
  const { action, hostedCheckoutUrl, checkoutSessionId } =
    resolvePaymentPresentation({
      action: paymentInfo.paymentAction,
      provider: hostedProvider,
      channel: paymentInfo.channel,
      legacyPayload: paymentInfo.paymentPayload,
      legacyValue: paymentInfo.qrUrl,
    });
  const actionUnavailableReason =
    paymentInfo.actionUnavailableReason ||
    (action?.type === 'sdk_confirm' && !hasPaymentSdkHandler(action.sdk)
      ? 'unsupported_action'
      : undefined);

  usePaymentActionUnavailableTracking({
    open,
    isLoggedIn,
    previewMode,
    shifuBid: courseId,
    orderId,
    channel: paymentInfo.channel,
    surface: 'mobile',
    reason: actionUnavailableReason,
  });

  const resolveDefaultChannel = useCallback(() => {
    if (paymentOptions) {
      return (
        defaultPaymentSelection(paymentOptions, wechatJsapiAvailable) ||
        PAY_CHANNEL_WECHAT
      );
    }
    if (wechatJsapiAvailable && wechatPaymentAvailable) {
      return PAY_CHANNEL_WECHAT_JSAPI;
    }
    if (alipayPaymentAvailable) {
      return PAY_CHANNEL_ZHIFUBAO;
    }
    if (wechatPaymentAvailable) {
      return PAY_CHANNEL_WECHAT_JSAPI;
    }
    if (isStripeAvailable) {
      return PAY_CHANNEL_STRIPE;
    }
    return defaultMobileChannel;
  }, [
    alipayPaymentAvailable,
    isStripeAvailable,
    paymentOptions,
    wechatJsapiAvailable,
    wechatPaymentAvailable,
  ]);

  const resolveRequestChannel = useCallback(
    (channel: string) => {
      if (channel === PAY_CHANNEL_WECHAT_JSAPI && !wechatJsapiAvailable) {
        return PAY_CHANNEL_WECHAT;
      }
      return channel;
    },
    [wechatJsapiAvailable],
  );

  const resolvePaymentChannel = useCallback(
    (channel: string): PaymentChannel | undefined => {
      return resolveRequestedPaymentProvider(
        paymentOptions,
        channel,
        normalizedPaymentChannels,
      );
    },
    [normalizedPaymentChannels, paymentOptions],
  );

  useEffect(() => {
    const isCurrentSupported =
      Boolean(
        selectedOption && ['qr', 'jsapi'].includes(selectedOption.action),
      ) ||
      (isHostedPaymentSelected && isStripeAvailable) ||
      (!isHostedPaymentSelected &&
        (((selectedOption
          ? selectedOption.method === 'wechat'
          : payChannel === PAY_CHANNEL_WECHAT_JSAPI) &&
          wechatPaymentAvailable) ||
          ((selectedOption
            ? selectedOption.method === 'alipay'
            : payChannel === PAY_CHANNEL_ZHIFUBAO) &&
            alipayPaymentAvailable)));
    if (isCurrentSupported) {
      return;
    }
    const fallbackChannel = resolveDefaultChannel();
    if (fallbackChannel && fallbackChannel !== payChannel) {
      setPayChannel(fallbackChannel);
      if (orderId) {
        refreshPayment({
          channel: resolveRequestChannel(fallbackChannel),
          paymentChannel: resolvePaymentChannel(fallbackChannel),
        });
      }
    }
  }, [
    alipayPaymentAvailable,
    isHostedPaymentSelected,
    isStripeAvailable,
    resolveDefaultChannel,
    resolvePaymentChannel,
    resolveRequestChannel,
    payChannel,
    orderId,
    refreshPayment,
    wechatPaymentAvailable,
    selectedOption,
  ]);

  const loadPayInfo = useCallback(async () => {
    if (!isLoggedIn) {
      return;
    }
    let nextOrderId = orderId;
    let nextSnapshot: Awaited<ReturnType<typeof initializeOrder>> = null;
    if (!nextOrderId) {
      const snapshot = await initializeOrder();
      nextSnapshot = snapshot;
      nextOrderId = snapshot?.order_id || '';
    }
    if (!nextOrderId) return;
    let nextChannel = payChannel;
    const snapshotOptions = nextSnapshot?.payment_options ?? paymentOptions;
    if (
      snapshotOptions &&
      !resolvePaymentOption(snapshotOptions, nextChannel)
    ) {
      nextChannel =
        defaultPaymentSelection(snapshotOptions, wechatJsapiAvailable) ||
        nextChannel;
      setPayChannel(nextChannel);
    }
    if (!snapshotOptions && !qrChannelEnabled && isStripeAvailable) {
      nextChannel = PAY_CHANNEL_STRIPE;
      if (nextChannel !== payChannel) {
        setPayChannel(nextChannel);
      }
    } else if (
      !snapshotOptions &&
      !isHostedPaymentSelected &&
      ((nextChannel === PAY_CHANNEL_WECHAT_JSAPI && !wechatPaymentAvailable) ||
        (nextChannel === PAY_CHANNEL_ZHIFUBAO && !alipayPaymentAvailable))
    ) {
      nextChannel = resolveDefaultChannel();
      if (nextChannel !== payChannel) {
        setPayChannel(nextChannel);
      }
    }
    await refreshPayment({
      channel: resolveRequestChannel(nextChannel),
      paymentChannel: resolvePaymentChannel(nextChannel),
      snapshot: nextSnapshot,
    });
  }, [
    alipayPaymentAvailable,
    initializeOrder,
    isLoggedIn,
    isStripeAvailable,
    isHostedPaymentSelected,
    orderId,
    payChannel,
    paymentOptions,
    wechatJsapiAvailable,
    qrChannelEnabled,
    refreshPayment,
    resolveDefaultChannel,
    resolvePaymentChannel,
    resolveRequestChannel,
    wechatPaymentAvailable,
  ]);

  const loadCourseInfo = useCallback(async () => {
    setPreviewInitLoading(true);
    try {
      const resp = await getCourseInfo(courseId, previewMode);
      setPreviewPrice(resp?.course_price);
    } catch {
      setPreviewPrice('0');
    } finally {
      setPreviewInitLoading(false);
    }
  }, [courseId, previewMode]);

  const handlePay = useCallback(async () => {
    if (isHostedPaymentSelected || isLoading) {
      return;
    }
    setPresentedQr(null);
    const paymentChannel = resolvePaymentChannel(payChannel);
    const payload = await refreshPayment({
      channel: resolveRequestChannel(payChannel),
      paymentChannel,
    });
    if (!payload || !('channel' in payload)) {
      return;
    }

    const paymentPayload = (payload.payment_payload ||
      paymentInfo.paymentPayload) as NativePaymentPayload;
    const resolvedAction = resolvePaymentAction(payload);
    const jsapiParams =
      payload.payment_contract_version !== undefined
        ? resolvedAction?.type === 'jsapi'
          ? resolvedAction.parameters
          : null
        : resolveJsapiParams(payload.qr_url, paymentPayload);
    if (jsapiParams) {
      const effectiveAttemptChannel = resolveRequestChannel(payChannel);
      const paymentAttempt = trackPaymentAttempt(effectiveAttemptChannel);
      try {
        await payByJsApi(jsapiParams);
        rememberProviderConfirmedChannel(paymentAttempt);
        const syncPaymentChannel = payload.payment_channel || paymentChannel;
        try {
          await syncOrderStatus(
            syncPaymentChannel
              ? {
                  paymentChannel: syncPaymentChannel,
                }
              : {},
          );
        } catch {
          trackPaymentPending(paymentAttempt);
          toast({
            title: t('module.pay.paymentStatusSyncPending'),
            variant: 'default',
          });
          return;
        }
        toast({
          title: t('module.pay.paySuccess'),
        });
      } catch (error) {
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
          paymentAttempt,
        );
      }
    } else if (
      resolvedAction?.type === 'redirect' ||
      resolvedAction?.type === 'qr'
    ) {
      trackPaymentAttempt(resolveRequestChannel(payChannel));
      if (
        resolvedAction.type === 'redirect' ||
        canOpenPaymentQr(resolvedAction.url)
      ) {
        window.open(resolvedAction.url, '_blank', 'noopener,noreferrer');
      } else {
        setPresentedQr({
          orderId,
          selection: payChannel,
          url: resolvedAction.url,
        });
      }
    }
  }, [
    isHostedPaymentSelected,
    isLoading,
    orderId,
    paymentInfo.paymentPayload,
    payByJsApi,
    payChannel,
    refreshPayment,
    rememberProviderConfirmedChannel,
    resolvePaymentChannel,
    resolveRequestChannel,
    syncOrderStatus,
    t,
    trackPaymentAttempt,
    trackPaymentPending,
    trackPaymentResult,
  ]);

  const onPayChannelChange = useCallback(
    (value: string) => {
      setPayChannel(value);
      if (orderId) {
        refreshPayment({
          channel: resolveRequestChannel(value),
          paymentChannel: resolvePaymentChannel(value),
        });
      }
    },
    [orderId, refreshPayment, resolvePaymentChannel, resolveRequestChannel],
  );

  const onPayChannelWechatClick = useCallback(() => {
    onPayChannelChange(wechatSelectionKey);
  }, [onPayChannelChange, wechatSelectionKey]);

  const onPayChannelZhifubaoClick = useCallback(() => {
    onPayChannelChange(alipaySelectionKey);
  }, [onPayChannelChange, alipaySelectionKey]);

  const onCouponCodeButtonClick = useCallback(() => {
    onCouponCodeModalOpen();
  }, [onCouponCodeModalOpen]);

  const closeCouponCodeModal = useCallback(() => {
    setCouponCodeInput('');
    onCouponCodeModalClose();
  }, [onCouponCodeModalClose]);

  const handleCouponCodeModalOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        closeCouponCodeModal();
      }
    },
    [closeCouponCodeModal],
  );

  const onStripeChannelClick = useCallback(() => {
    onPayChannelChange(PAY_CHANNEL_STRIPE);
  }, [onPayChannelChange]);

  const handleStripeSuccess = useCallback(
    async (attempt?: LearnerPaymentAttemptContext) => {
      try {
        rememberProviderConfirmedChannel(attempt);
        if (hostedProvider === 'stripe') {
          await syncOrderStatus();
        } else {
          await syncOrderStatus({ paymentChannel: hostedProvider });
        }
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
      hostedProvider,
      syncOrderStatus,
      t,
      trackPaymentPending,
    ],
  );

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
    [t, trackPaymentPending, trackPaymentResult],
  );

  const handleStripeConfirmationUnavailable = useCallback(
    (attempt: LearnerPaymentAttemptContext) => {
      trackPaymentPending(attempt);
    },
    [trackPaymentPending],
  );

  const handleHostedCheckout = useCallback(() => {
    if (!isLoading && hostedCheckoutUrl) {
      trackPaymentAttempt(hostedAttemptChannel);
      if (hostedProvider === 'stripe' && checkoutSessionId && orderId) {
        rememberStripeCheckoutSession(checkoutSessionId, orderId);
      }
      window.location.href = hostedCheckoutUrl;
    }
  }, [
    isLoading,
    orderId,
    checkoutSessionId,
    hostedCheckoutUrl,
    hostedProvider,
    hostedAttemptChannel,
    trackPaymentAttempt,
  ]);

  const onCouponCodeOkClick = useCallback(async () => {
    if (!couponCodeInput) {
      return;
    }
    const snapshot = await applyCoupon({
      code: couponCodeInput,
      channel: resolveRequestChannel(payChannel),
      paymentChannel: resolvePaymentChannel(payChannel),
    });
    await refreshPayment({
      channel: resolveRequestChannel(payChannel),
      paymentChannel: resolvePaymentChannel(payChannel),
      snapshot,
    });
    trackLearnerPaymentEventSafely(trackEvent, 'learner_coupon_apply', {
      shifu_bid: courseId,
      outcome: 'success',
    });
    closeCouponCodeModal();
  }, [
    applyCoupon,
    closeCouponCodeModal,
    couponCodeInput,
    courseId,
    payChannel,
    refreshPayment,
    resolvePaymentChannel,
    resolveRequestChannel,
    trackEvent,
  ]);

  const triggerCancel = useCallback(() => {
    skipNextCancelEventRef.current = true;
    trackModalDismiss();
    onCancel?.();
  }, [onCancel, trackModalDismiss]);

  const onLoginButtonClick = useCallback(() => {
    triggerCancel();
    shifu.loginTools.openLogin();
  }, [triggerCancel]);

  useEffect(() => {
    if (!open || !isLoggedIn) {
      initialPaymentRequestedRef.current = false;
      return;
    }
    if (initialPaymentRequestedRef.current) {
      return;
    }
    initialPaymentRequestedRef.current = true;
    loadPayInfo();
  }, [isLoggedIn, loadPayInfo, open]);

  useEffect(() => {
    if (!orderId && !hookInitLoading && !isLoading) {
      // Only release the one-shot guard after the current payment bootstrap settles.
      initialPaymentRequestedRef.current = false;
    }
  }, [hookInitLoading, isLoading, orderId]);

  useEffect(() => {
    if (!open || isLoggedIn) {
      return;
    }
    loadCourseInfo();
  }, [isLoggedIn, loadCourseInfo, open]);

  function handleCancel(nextOpen: boolean) {
    if (!nextOpen) {
      initialPaymentRequestedRef.current = false;
      if (skipNextCancelEventRef.current) {
        skipNextCancelEventRef.current = false;
        return;
      }
      trackModalDismiss();
      onCancel?.();
    }
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={handleCancel}
      >
        <DialogContent className='w-full'>
          <DialogHeader className='sr-only'>
            <DialogTitle>{t('module.pay.title')}</DialogTitle>
          </DialogHeader>
          <div className={styles.payModalContent}>
            {isCompleted ? (
              <CompletedSection />
            ) : (
              <>
                {ready ? (
                  <>
                    <div className={styles.payInfoTitle}>
                      {t('module.pay.finalPrice')}
                    </div>
                    <div className={styles.priceWrapper}>
                      <div className={cn(styles.price)}>
                        <span className={styles.priceSign}>
                          {currencySymbol}
                        </span>
                        <span className={styles.priceNumber}>
                          {displayPrice}
                        </span>
                      </div>
                    </div>

                    {displayOriginalPrice && (
                      <div
                        className={styles.originalPriceWrapper}
                        style={{
                          visibility:
                            displayOriginalPrice === displayPrice
                              ? 'hidden'
                              : 'visible',
                        }}
                      >
                        <div className={styles.originalPrice}>
                          {displayOriginalPrice}
                        </div>
                      </div>
                    )}
                    {priceItems && priceItems.length > 0 && (
                      <div className={styles.priceItemsWrapper}>
                        {priceItems.map((item, index) => {
                          return (
                            <div
                              className={styles.priceItem}
                              key={index}
                            >
                              <div className={styles.priceItemName}>
                                {item.price_name}
                              </div>
                              <div className={styles.priceItemPrice}>
                                {item.price}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {isLoggedIn ? (
                      <>
                        {qrChannelEnabled ? (
                          <div className={styles.payChannelWrapper}>
                            <RadioGroup
                              value={radioSelectionKey}
                              onValueChange={onPayChannelChange}
                            >
                              {paymentOptions
                                ?.filter(
                                  option =>
                                    option.action === 'qr' &&
                                    !['wechat', 'alipay'].includes(
                                      option.method,
                                    ),
                                )
                                .map(option => (
                                  <button
                                    key={option.id}
                                    type='button'
                                    className={cn(
                                      styles.payChannelRow,
                                      selectedOption?.id === option.id &&
                                        styles.selected,
                                    )}
                                    onClick={() =>
                                      onPayChannelChange(
                                        paymentSelectionKey(
                                          option,
                                          paymentOptions,
                                        ),
                                      )
                                    }
                                  >
                                    <span className={styles.payChannelTitle}>
                                      {t(option.label_key)}
                                    </span>
                                  </button>
                                ))}
                              {wechatPaymentAvailable ? (
                                <div
                                  className={cn(
                                    styles.payChannelRow,
                                    (selectedOption
                                      ? selectedOption.method === 'wechat'
                                      : payChannel ===
                                        PAY_CHANNEL_WECHAT_JSAPI) &&
                                      styles.selected,
                                  )}
                                  data-clickable='true'
                                  onClick={onPayChannelWechatClick}
                                >
                                  <div className={styles.payChannelBasic}>
                                    <Image
                                      className={styles.payChannelIcon}
                                      src={weixinIcon}
                                      alt={t('module.pay.wechatPay')}
                                    />
                                    <span className={styles.payChannelTitle}>
                                      {t('module.pay.wechatPay')}
                                    </span>
                                  </div>
                                  <RadioGroupItem
                                    value={wechatSelectionKey}
                                    onClick={event => event.stopPropagation()}
                                    className={styles.payChannelRadio}
                                  />
                                </div>
                              ) : null}
                              {alipayPaymentAvailable ? (
                                <div
                                  className={cn(
                                    styles.payChannelRow,
                                    (selectedOption
                                      ? selectedOption.method === 'alipay'
                                      : payChannel === PAY_CHANNEL_ZHIFUBAO) &&
                                      styles.selected,
                                  )}
                                  data-clickable='true'
                                  onClick={onPayChannelZhifubaoClick}
                                >
                                  <div className={styles.payChannelBasic}>
                                    <Image
                                      className={styles.payChannelIcon}
                                      src={zhifuboIcon}
                                      alt={t('module.pay.alipay')}
                                    />
                                    <span className={styles.payChannelTitle}>
                                      {t('module.pay.alipay')}
                                    </span>
                                  </div>
                                  <RadioGroupItem
                                    value={alipaySelectionKey}
                                    onClick={event => event.stopPropagation()}
                                    className={styles.payChannelRadio}
                                  />
                                </div>
                              ) : null}
                            </RadioGroup>
                          </div>
                        ) : null}
                        {isStripeAvailable ? (
                          <div className={styles.stripeSelector}>
                            {paymentOptions ? (
                              hostedOptions.map(option => (
                                <MainButtonM
                                  key={option.id}
                                  className={cn(
                                    styles.stripeButton,
                                    selectedOption?.id === option.id &&
                                      styles.stripeButtonActive,
                                  )}
                                  fill={
                                    selectedOption?.id === option.id
                                      ? 'solid'
                                      : 'none'
                                  }
                                  onClick={() => onPayChannelChange(option.id)}
                                >
                                  {t(
                                    option.provider === 'stripe'
                                      ? 'module.pay.payChannelStripeCard'
                                      : option.label_key,
                                  )}
                                </MainButtonM>
                              ))
                            ) : (
                              <MainButtonM
                                className={cn(
                                  styles.stripeButton,
                                  isHostedPaymentSelected &&
                                    styles.stripeButtonActive,
                                )}
                                fill={
                                  isHostedPaymentSelected ? 'solid' : 'none'
                                }
                                onClick={onStripeChannelClick}
                              >
                                {t('module.pay.payChannelStripeCard')}
                              </MainButtonM>
                            )}
                          </div>
                        ) : null}
                        {actionUnavailableReason ? (
                          <div className={styles.stripeHint}>
                            <p>{t('module.pay.stripeError')}</p>
                            <MainButtonM onClick={loadPayInfo}>
                              {t('module.pay.clickRefresh')}
                            </MainButtonM>
                          </div>
                        ) : isHostedPaymentSelected ? (
                          <div className={styles.stripePanel}>
                            {action?.type !== 'sdk_confirm' ? (
                              <div className={styles.stripeCheckoutBlock}>
                                <p className={styles.stripeHint}>
                                  {t(
                                    selectedOption &&
                                      selectedOption.provider !== 'stripe'
                                      ? 'module.pay.title'
                                      : 'module.pay.stripeCheckoutHint',
                                  )}
                                </p>
                                <MainButtonM
                                  className={styles.payButton}
                                  onClick={handleHostedCheckout}
                                  disabled={isLoading || !hostedCheckoutUrl}
                                >
                                  {t(
                                    selectedOption &&
                                      selectedOption.provider !== 'stripe'
                                      ? 'module.pay.pay'
                                      : 'module.pay.goToStripeCheckout',
                                  )}
                                </MainButtonM>
                              </div>
                            ) : !isLoading ? (
                              <PaymentSdkForm
                                action={action}
                                publishableKey={stripePublishableKey || ''}
                                onAttempt={() =>
                                  trackPaymentAttempt(hostedAttemptChannel)
                                }
                                onConfirmSuccess={handleStripeSuccess}
                                onConfirmationUnavailable={
                                  handleStripeConfirmationUnavailable
                                }
                                onError={handleStripeError}
                              />
                            ) : null}
                          </div>
                        ) : qrChannelEnabled ? (
                          <>
                            <div className={styles.buttonWrapper}>
                              <MainButtonM
                                className={styles.payButton}
                                onClick={handlePay}
                                disabled={isLoading}
                              >
                                {t('module.pay.pay')}
                              </MainButtonM>
                            </div>
                            {!isLoading &&
                            presentedQr?.orderId === orderId &&
                            presentedQr.selection === payChannel &&
                            presentedQr.url === paymentInfo.qrUrl ? (
                              <div className='mt-4 flex justify-center'>
                                <QRCodeSVG value={presentedQr.url} />
                              </div>
                            ) : null}
                          </>
                        ) : (
                          <div className={styles.stripeHint}>
                            {t('module.pay.stripeError')}
                          </div>
                        )}
                        <div className={styles.couponCodeWrapper}>
                          <MainButtonM
                            className={styles.couponCodeButton}
                            fill='none'
                            onClick={onCouponCodeButtonClick}
                          >
                            {!appliedCouponCode
                              ? t('module.groupon.useOtherPayment')
                              : t('module.groupon.modify')}
                          </MainButtonM>
                        </div>
                        <PayModalFooter className={styles.payModalFooter} />
                      </>
                    ) : (
                      <div className={styles.loginButtonWrapper}>
                        <MainButtonM onClick={onLoginButtonClick}>
                          {t('module.auth.login')}
                        </MainButtonM>
                      </div>
                    )}
                  </>
                ) : (
                  <></>
                )}
              </>
            )}

            {/* <div className={styles.payInfoWrapper}>
              <Image
                className={styles.payInfo}
                src={payInfoBg}
                alt={'productDescription'}
                width={payInfoBg.width}
                height={payInfoBg.height}
              />
            </div> */}
          </div>
        </DialogContent>
      </Dialog>

      {couponCodeModalOpen && (
        <Dialog
          open={couponCodeModalOpen}
          onOpenChange={handleCouponCodeModalOpenChange}
        >
          <DialogContent className={cn('w-5/6', styles.couponCodeModal)}>
            <DialogHeader>
              <DialogTitle>{t('module.groupon.title')}</DialogTitle>
            </DialogHeader>
            <div className={styles.couponCodeInputWrapper}>
              <SettingInputM
                title={t('module.groupon.title')}
                value={couponCodeInput}
                onChange={value => setCouponCodeInput(value)}
              />
            </div>
            <div className={styles.buttonWrapper}>
              <MainButtonM
                onClick={onCouponCodeOkClick}
                className={styles.okButton}
              >
                {t('common.core.ok')}
              </MainButtonM>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
};

export default memo(PayModalM);
