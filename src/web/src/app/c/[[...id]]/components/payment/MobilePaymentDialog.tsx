import styles from './MobilePaymentDialog.module.scss';

import { memo, useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { cn } from '@/lib/utils';

import Image from 'next/image';
import weixinIcon from '@/assets/learner/weixin.png';
import zhifuboIcon from '@/assets/learner/zhifubao.png';
import paySuccessBg from '@/assets/learner/pay-success@2x.png';

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
} from './payment-constants';
import { isWechatJsapiAvailable } from './wechat-jsapi';
import MobileActionButton from '@/components/mobile/MobileActionButton';
import StripeCardForm from './StripeCardForm';

import { usePaymentFlow } from './hooks/use-payment-flow';
import {
  usePaymentAnalytics,
  usePaymentAnalyticsLifecycle,
  usePaymentOutcomeHandlers,
} from './hooks/use-payment-analytics';
import { useWechat } from '@/hooks/use-wechat';

import { toast } from '@/hooks/use-toast';

import { inWechat } from '@/constants/ui-constants';
import { useDisclosure } from '@/hooks/use-disclosure';
import { MobileSettingInput } from '@/components/mobile/MobileSettingInput';
import PayModalFooter from './PayModalFooter';

import { getStringEnv } from '@/lib/env-utils';
import { useUserStore } from '@/store';
import { shifu } from '@/lib/shifu/shifu-runtime';
import { useEnvStore } from '@/store/env-store';
import { useSystemStore } from '@/store/use-system-store';
import type {
  NativePaymentPayload,
  PaymentChannel,
  StripePaymentPayload,
} from '@/api/order';
import { getCourseInfo } from '@/api/course';
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

const isJsapiParams = (value: unknown): value is Record<string, string> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  return Object.values(value).every(item => typeof item === 'string');
};

const resolveJsapiParams = (
  qrUrl: unknown,
  paymentPayload: NativePaymentPayload,
) => {
  if (isJsapiParams(paymentPayload.jsapi_params)) {
    return paymentPayload.jsapi_params;
  }
  const credential = paymentPayload.credential || {};
  const wxPubCredential = credential.wx_pub;
  if (isJsapiParams(wxPubCredential)) {
    return wxPubCredential;
  }
  if (isJsapiParams(qrUrl)) {
    return qrUrl;
  }
  return null;
};

export const MobilePaymentDialog = ({
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
  const skipNextCancelEventRef = useRef(false);

  const courseId = getStringEnv('courseId');
  const { isLoggedIn, userInfo } = useUserStore(
    useShallow(state => ({
      isLoggedIn: state.isLoggedIn,
      userInfo: state.userInfo,
    })),
  );
  const { t } = useTranslation();
  const { payByJsApi } = useWechat();
  const paymentAnalytics = usePaymentAnalytics({
    courseId,
    surface: 'mobile',
  });
  const { trackPaymentAttempt, trackPaymentResult, trackCouponApplied } =
    paymentAnalytics;
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
  const { trackModalDismiss } = usePaymentAnalyticsLifecycle(paymentAnalytics, {
    open,
    ready,
    orderId,
    isTimeout,
    displayPrice,
    currencySymbol,
  });
  const initialPaymentRequestedRef = useRef(false);
  const normalizedPaymentChannels = useMemo(
    () => (paymentChannels || []).map(channel => channel.trim().toLowerCase()),
    [paymentChannels],
  );
  const pingxxChannelEnabled = normalizedPaymentChannels.includes('pingxx');
  const alipayChannelEnabled = normalizedPaymentChannels.includes('alipay');
  const wechatpayChannelEnabled =
    normalizedPaymentChannels.includes('wechatpay');
  const stripeChannelEnabled = normalizedPaymentChannels.includes('stripe');
  const isStripeAvailable =
    stripeChannelEnabled &&
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
  const wechatPaymentAvailable =
    pingxxChannelEnabled || wechatpayChannelEnabled;
  const alipayPaymentAvailable = pingxxChannelEnabled || alipayChannelEnabled;
  const qrChannelEnabled = wechatPaymentAvailable || alipayPaymentAvailable;
  const isStripeSelected = payChannel.startsWith('stripe');
  const stripePayload = (paymentInfo?.paymentPayload ||
    {}) as StripePaymentPayload;
  const nativePayload = useMemo(
    () => (paymentInfo?.paymentPayload || {}) as NativePaymentPayload,
    [paymentInfo?.paymentPayload],
  );
  const stripeCheckoutUrl =
    stripePayload.checkout_session_url || paymentInfo?.qrUrl || '';
  const stripeMode = (stripePayload.mode || '').toLowerCase();
  const {
    handleStripeSuccess,
    handleStripeCheckout,
    handleStripeError,
    handleStripeConfirmationUnavailable,
    settleWechatJsapiPayment,
  } = usePaymentOutcomeHandlers(paymentAnalytics, {
    orderId,
    stripeCheckoutUrl,
    stripeCheckoutSessionId: stripePayload.checkout_session_id,
    syncOrderStatus,
    toast,
  });

  const resolveDefaultChannel = useCallback(() => {
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
      if (channel.startsWith('stripe')) {
        return 'stripe';
      }
      if (channel === PAY_CHANNEL_ZHIFUBAO) {
        return alipayChannelEnabled ? 'alipay' : 'pingxx';
      }
      if (
        channel === PAY_CHANNEL_WECHAT ||
        channel === PAY_CHANNEL_WECHAT_JSAPI
      ) {
        return wechatpayChannelEnabled ? 'wechatpay' : 'pingxx';
      }
      return undefined;
    },
    [alipayChannelEnabled, wechatpayChannelEnabled],
  );

  useEffect(() => {
    const isCurrentSupported =
      (isStripeSelected && isStripeAvailable) ||
      (!isStripeSelected &&
        ((payChannel === PAY_CHANNEL_WECHAT_JSAPI && wechatPaymentAvailable) ||
          (payChannel === PAY_CHANNEL_ZHIFUBAO && alipayPaymentAvailable)));
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
    isStripeSelected,
    isStripeAvailable,
    resolveDefaultChannel,
    resolvePaymentChannel,
    resolveRequestChannel,
    payChannel,
    orderId,
    refreshPayment,
    wechatPaymentAvailable,
  ]);

  const loadPayInfo = useCallback(async () => {
    if (!isLoggedIn) {
      return;
    }
    let nextOrderId = orderId;
    let nextSnapshot = null;
    if (!nextOrderId) {
      const snapshot = await initializeOrder();
      nextSnapshot = snapshot;
      nextOrderId = snapshot?.order_id || '';
    }
    if (!nextOrderId) return;
    let nextChannel = payChannel;
    if (!qrChannelEnabled && isStripeAvailable) {
      nextChannel = PAY_CHANNEL_STRIPE;
      if (nextChannel !== payChannel) {
        setPayChannel(nextChannel);
      }
    } else if (
      !isStripeSelected &&
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
    isStripeSelected,
    orderId,
    payChannel,
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
    if (isStripeSelected) {
      return;
    }
    const paymentChannel = resolvePaymentChannel(payChannel);
    const payload = await refreshPayment({
      channel: resolveRequestChannel(payChannel),
      paymentChannel,
    });
    if (!payload || !('qr_url' in payload)) {
      return;
    }

    const paymentPayload = (payload.payment_payload ||
      nativePayload) as NativePaymentPayload;
    const jsapiParams = resolveJsapiParams(payload.qr_url, paymentPayload);
    if (jsapiParams) {
      const effectiveAttemptChannel = resolveRequestChannel(payChannel);
      const paymentAttempt = trackPaymentAttempt(effectiveAttemptChannel);
      const syncPaymentChannel = payload.payment_channel || paymentChannel;
      await settleWechatJsapiPayment({
        attempt: paymentAttempt,
        pay: () => payByJsApi(jsapiParams),
        syncParams: syncPaymentChannel
          ? {
              paymentChannel: syncPaymentChannel,
            }
          : {},
      });
    } else if (typeof payload.qr_url === 'string' && payload.qr_url) {
      trackPaymentAttempt(resolveRequestChannel(payChannel));
      window.open(payload.qr_url);
    }
  }, [
    isStripeSelected,
    nativePayload,
    payByJsApi,
    payChannel,
    refreshPayment,
    resolvePaymentChannel,
    resolveRequestChannel,
    settleWechatJsapiPayment,
    trackPaymentAttempt,
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
    onPayChannelChange(PAY_CHANNEL_WECHAT_JSAPI);
  }, [onPayChannelChange]);

  const onPayChannelZhifubaoClick = useCallback(() => {
    onPayChannelChange(PAY_CHANNEL_ZHIFUBAO);
  }, [onPayChannelChange]);

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
    trackCouponApplied();
    closeCouponCodeModal();
  }, [
    applyCoupon,
    closeCouponCodeModal,
    couponCodeInput,
    payChannel,
    refreshPayment,
    resolvePaymentChannel,
    resolveRequestChannel,
    trackCouponApplied,
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
                              value={payChannel}
                              onValueChange={onPayChannelChange}
                            >
                              {wechatPaymentAvailable ? (
                                <div
                                  className={cn(
                                    styles.payChannelRow,
                                    payChannel === PAY_CHANNEL_WECHAT_JSAPI &&
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
                                    value={PAY_CHANNEL_WECHAT_JSAPI}
                                    className={styles.payChannelRadio}
                                  />
                                </div>
                              ) : null}
                              {alipayPaymentAvailable ? (
                                <div
                                  className={cn(
                                    styles.payChannelRow,
                                    payChannel === PAY_CHANNEL_ZHIFUBAO &&
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
                                    value={PAY_CHANNEL_ZHIFUBAO}
                                    className={styles.payChannelRadio}
                                  />
                                </div>
                              ) : null}
                            </RadioGroup>
                          </div>
                        ) : null}
                        {isStripeAvailable ? (
                          <div className={styles.stripeSelector}>
                            <MobileActionButton
                              className={cn(
                                styles.stripeButton,
                                isStripeSelected && styles.stripeButtonActive,
                              )}
                              fill={isStripeSelected ? 'solid' : 'none'}
                              onClick={onStripeChannelClick}
                            >
                              {t('module.pay.payChannelStripeCard')}
                            </MobileActionButton>
                          </div>
                        ) : null}
                        {isStripeSelected ? (
                          <div className={styles.stripePanel}>
                            {stripeMode === 'checkout_session' ||
                            !stripePayload.client_secret ? (
                              <div className={styles.stripeCheckoutBlock}>
                                <p className={styles.stripeHint}>
                                  {t('module.pay.stripeCheckoutHint')}
                                </p>
                                <MobileActionButton
                                  className={styles.payButton}
                                  onClick={handleStripeCheckout}
                                  disabled={!stripeCheckoutUrl}
                                >
                                  {t('module.pay.goToStripeCheckout')}
                                </MobileActionButton>
                              </div>
                            ) : (
                              <StripeCardForm
                                clientSecret={stripePayload.client_secret}
                                publishableKey={stripePublishableKey || ''}
                                onAttempt={() =>
                                  trackPaymentAttempt(PAY_CHANNEL_STRIPE)
                                }
                                onConfirmSuccess={handleStripeSuccess}
                                onConfirmationUnavailable={
                                  handleStripeConfirmationUnavailable
                                }
                                onError={handleStripeError}
                              />
                            )}
                          </div>
                        ) : qrChannelEnabled ? (
                          <div className={styles.buttonWrapper}>
                            <MobileActionButton
                              className={styles.payButton}
                              onClick={handlePay}
                            >
                              {t('module.pay.pay')}
                            </MobileActionButton>
                          </div>
                        ) : (
                          <div className={styles.stripeHint}>
                            {t('module.pay.stripeError')}
                          </div>
                        )}
                        <div className={styles.couponCodeWrapper}>
                          <MobileActionButton
                            className={styles.couponCodeButton}
                            fill='none'
                            onClick={onCouponCodeButtonClick}
                          >
                            {!appliedCouponCode
                              ? t('module.groupon.useOtherPayment')
                              : t('module.groupon.modify')}
                          </MobileActionButton>
                        </div>
                        <PayModalFooter className={styles.payModalFooter} />
                      </>
                    ) : (
                      <div className={styles.loginButtonWrapper}>
                        <MobileActionButton onClick={onLoginButtonClick}>
                          {t('module.auth.login')}
                        </MobileActionButton>
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
              <MobileSettingInput
                title={t('module.groupon.title')}
                value={couponCodeInput}
                onChange={value => setCouponCodeInput(value)}
              />
            </div>
            <div className={styles.buttonWrapper}>
              <MobileActionButton
                onClick={onCouponCodeOkClick}
                className={styles.okButton}
              >
                {t('common.core.ok')}
              </MobileActionButton>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
};

export default memo(MobilePaymentDialog);
