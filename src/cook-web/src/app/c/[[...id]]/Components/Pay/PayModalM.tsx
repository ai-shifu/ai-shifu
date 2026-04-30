import styles from './PayModalM.module.scss';

import { memo, useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { cn } from '@/lib/utils';

import Image from 'next/image';
import weixinIcon from '@/c-assets/newchat/weixin.png';
import zhifuboIcon from '@/c-assets/newchat/zhifubao.png';
import paySuccessBg from '@/c-assets/newchat/pay-success@2x.png';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { RadioGroup, RadioGroupItem } from '@/components/ui/RadioGroup';

import {
  PAY_CHANNEL_ALIPAY_WAP,
  PAY_CHANNEL_WECHAT,
  PAY_CHANNEL_WECHAT_JSAPI,
  PAY_CHANNEL_WECHAT_WAP,
  PAY_CHANNEL_ZHIFUBAO,
  PAY_CHANNEL_STRIPE,
} from './constans';
import MainButtonM from '@/c-components/m/MainButtonM';
import StripeCardForm from './StripeCardForm';

import { usePaymentFlow } from './hooks/usePaymentFlow';
import { useWechat } from '@/c-common/hooks/useWechat';

import { toast } from '@/hooks/useToast';

import { inWechat } from '@/c-constants/uiConstants';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { SettingInputM } from '@/c-components/m/SettingInputM';
import PayModalFooter from './PayModalFooter';

import { getStringEnv } from '@/c-utils/envUtils';
import { useUserStore } from '@/store';
import { shifu } from '@/c-service/Shifu';
import { useEnvStore } from '@/c-store/envStore';
import { useSystemStore } from '@/c-store/useSystemStore';
import type {
  NativePaymentPayload,
  PaymentChannel,
  PingxxPaymentPayload,
  StripePaymentPayload,
} from '@/c-api/order';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import { getCourseInfo } from '@/c-api/course';
import { useTracking } from '@/c-common/hooks/useTracking';
import { getCurrencyCode } from '@/c-utils/currency';
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

const isJsapiParams = (value: unknown): value is Record<string, string> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  return Object.values(value).every(item => typeof item === 'string');
};

const resolveJsapiParams = (
  qrUrl: unknown,
  paymentPayload: NativePaymentPayload | PingxxPaymentPayload,
) => {
  if (
    'jsapi_params' in paymentPayload &&
    isJsapiParams(paymentPayload.jsapi_params)
  ) {
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

export const PayModalM = ({
  open = false,
  onCancel,
  onOk,
  type = '',
  payload = {},
}) => {
  const [payChannel, setPayChannel] = useState(PAY_CHANNEL_WECHAT_JSAPI);
  const [couponCodeInput, setCouponCodeInput] = useState('');
  const [previewPrice, setPreviewPrice] = useState('0');
  const [previewInitLoading, setPreviewInitLoading] = useState(true);
  const modalViewTrackedRef = useRef(false);
  const skipNextCancelEventRef = useRef(false);

  const courseId = getStringEnv('courseId');
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const { payByJsApi } = useWechat();
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
  } = useEnvStore(
    useShallow(state => ({
      stripePublishableKey: state.stripePublishableKey,
      stripeEnabled: state.stripeEnabled,
      paymentChannels: state.paymentChannels,
      currencySymbol: state.currencySymbol || '¥',
    })),
  );
  const initialPaymentRequestedRef = useRef(false);
  const currencyCode = useMemo(
    () => getCurrencyCode(currencySymbol),
    [currencySymbol],
  );
  const emitCancelEvent = useCallback(() => {
    trackEvent('learner_pay_cancel', {
      shifu_bid: courseId,
      order_id: orderId || '',
      cancel_stage: 'modal',
    });
  }, [courseId, orderId, trackEvent]);

  useEffect(() => {
    if (!open) {
      modalViewTrackedRef.current = false;
      return;
    }
    if (!ready) {
      return;
    }
    if (modalViewTrackedRef.current) {
      return;
    }
    modalViewTrackedRef.current = true;
    trackEvent('learner_pay_modal_view', {
      shifu_bid: courseId,
      price: displayPrice || '0',
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
  const isStripeAvailable =
    stripeChannelEnabled &&
    stripeEnabled === 'true' &&
    Boolean(stripePublishableKey);
  const isWechatBrowser = useMemo(
    () => typeof navigator !== 'undefined' && inWechat(),
    [],
  );
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
  const mobileWechatChannel =
    isWechatBrowser
      ? PAY_CHANNEL_WECHAT_JSAPI
      : pingxxChannelEnabled
        ? PAY_CHANNEL_WECHAT_WAP
        : PAY_CHANNEL_WECHAT;
  const mobileAlipayChannel = pingxxChannelEnabled
    ? PAY_CHANNEL_ALIPAY_WAP
    : PAY_CHANNEL_ZHIFUBAO;
  const stripeCheckoutUrl =
    stripePayload.checkout_session_url ||
    (typeof paymentInfo?.qrUrl === 'string' ? paymentInfo.qrUrl : '') ||
    '';
  const stripeMode = (stripePayload.mode || '').toLowerCase();
  const isPingxxRedirectChannel =
    payChannel === PAY_CHANNEL_WECHAT_WAP || payChannel === PAY_CHANNEL_ALIPAY_WAP;

  const resolveDefaultChannel = useCallback(() => {
    if (wechatPaymentAvailable) {
      return mobileWechatChannel;
    }
    if (alipayPaymentAvailable) {
      return mobileAlipayChannel;
    }
    if (isStripeAvailable) {
      return PAY_CHANNEL_STRIPE;
    }
    return mobileWechatChannel;
  }, [
    alipayPaymentAvailable,
    isStripeAvailable,
    mobileAlipayChannel,
    mobileWechatChannel,
    wechatPaymentAvailable,
  ]);

  const handlePaymentRefreshError = useCallback(
    (error: unknown) => {
      const message =
        error instanceof Error && error.message
          ? error.message
          : t('module.pay.payFailed');
      toast({
        title: message,
        variant: 'destructive',
      });
    },
    [t],
  );

  const buildPaymentParams = useCallback(
    (channel: string, targetOrderId?: string) => {
      let paymentChannel: PaymentChannel | undefined;
      if (channel.startsWith('stripe')) {
        paymentChannel = 'stripe';
      } else if (channel === PAY_CHANNEL_ALIPAY_WAP) {
        paymentChannel = 'pingxx';
      } else if (channel === PAY_CHANNEL_ZHIFUBAO) {
        paymentChannel = alipayChannelEnabled ? 'alipay' : 'pingxx';
      } else if (channel === PAY_CHANNEL_WECHAT_WAP) {
        paymentChannel = 'pingxx';
      } else if (
        channel === PAY_CHANNEL_WECHAT ||
        channel === PAY_CHANNEL_WECHAT_JSAPI
      ) {
        paymentChannel = wechatpayChannelEnabled ? 'wechatpay' : 'pingxx';
      }

      const buildPingxxReturnUrl = () => {
        const effectiveOrderId = targetOrderId || orderId;
        if (typeof window === 'undefined' || !effectiveOrderId || !courseId) {
          return undefined;
        }
        const searchParams = new URLSearchParams({
          order_id: effectiveOrderId,
          course_id: courseId,
          redirect: `${window.location.pathname}${window.location.search}`,
        });
        return `/payment/pingxx/result?${searchParams.toString()}`;
      };

      const buildPingxxCancelUrl = () => {
        if (typeof window === 'undefined') {
          return undefined;
        }
        return `${window.location.pathname}${window.location.search}`;
      };

      const needsPingxxRedirect =
        channel === PAY_CHANNEL_WECHAT_WAP || channel === PAY_CHANNEL_ALIPAY_WAP;

      return {
        channel,
        paymentChannel,
        returnUrl: needsPingxxRedirect
          ? buildPingxxReturnUrl()
          : undefined,
        cancelUrl:
          channel === PAY_CHANNEL_ALIPAY_WAP
            ? buildPingxxCancelUrl()
            : undefined,
      };
    },
    [
      alipayChannelEnabled,
      courseId,
      orderId,
      wechatpayChannelEnabled,
    ],
  );

  useEffect(() => {
    const isCurrentSupported =
      (isStripeSelected && isStripeAvailable) ||
      (!isStripeSelected &&
        (payChannel === mobileWechatChannel ||
          payChannel === mobileAlipayChannel));
    if (isCurrentSupported) {
      return;
    }
    const fallbackChannel = resolveDefaultChannel();
    if (fallbackChannel && fallbackChannel !== payChannel) {
      setPayChannel(fallbackChannel);
      if (orderId) {
        void refreshPayment(buildPaymentParams(fallbackChannel, orderId)).catch(
          handlePaymentRefreshError,
        );
      }
    }
  }, [
    buildPaymentParams,
    handlePaymentRefreshError,
    isStripeSelected,
    isStripeAvailable,
    mobileAlipayChannel,
    mobileWechatChannel,
    resolveDefaultChannel,
    payChannel,
    orderId,
    refreshPayment,
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
    if (!nextOrderId) {
      return;
    }
    let nextChannel = payChannel;
    if (!qrChannelEnabled && isStripeAvailable) {
      nextChannel = PAY_CHANNEL_STRIPE;
      if (nextChannel !== payChannel) {
        setPayChannel(nextChannel);
      }
    } else if (
      !isStripeSelected &&
      nextChannel !== mobileWechatChannel &&
      nextChannel !== mobileAlipayChannel
    ) {
      nextChannel = resolveDefaultChannel();
      if (nextChannel !== payChannel) {
        setPayChannel(nextChannel);
      }
    }
    try {
      await refreshPayment({
        ...buildPaymentParams(nextChannel, nextOrderId),
        snapshot: nextSnapshot,
      });
    } catch (error) {
      handlePaymentRefreshError(error);
    }
  }, [
    buildPaymentParams,
    handlePaymentRefreshError,
    initializeOrder,
    isLoggedIn,
    isStripeAvailable,
    isStripeSelected,
    mobileAlipayChannel,
    mobileWechatChannel,
    orderId,
    payChannel,
    qrChannelEnabled,
    refreshPayment,
    resolveDefaultChannel,
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
    let payload: Awaited<ReturnType<typeof refreshPayment>>;
    try {
      payload = await refreshPayment(buildPaymentParams(payChannel, orderId));
    } catch (error) {
      handlePaymentRefreshError(error);
      return;
    }
    if (!payload || !('qr_url' in payload)) {
      return;
    }

    const paymentPayload = (payload.payment_payload ||
      nativePayload) as NativePaymentPayload | PingxxPaymentPayload;
    const jsapiParams = resolveJsapiParams(payload.qr_url, paymentPayload);
    if (jsapiParams) {
      try {
        await payByJsApi(jsapiParams);
        const syncPaymentChannel = payload.payment_channel;
        try {
          await syncOrderStatus(
            syncPaymentChannel ? { paymentChannel: syncPaymentChannel } : {},
          );
        } catch {
          // The polling loop continues syncing native payments after the bridge reports success.
        }
        toast({
          title: t('module.pay.paySuccess'),
        });
      } catch {
        toast({
          title: t('module.pay.payFailed'),
          variant: 'destructive',
        });
      }
    } else if (isPingxxRedirectChannel) {
      const redirectUrl =
        (payload.payment_payload as PingxxPaymentPayload | undefined)
          ?.redirect_url ||
        (typeof payload.qr_url === 'string' ? payload.qr_url : '');
      if (!redirectUrl) {
        toast({
          title: t('module.pay.payFailed'),
          variant: 'destructive',
        });
        return;
      }
      window.location.href = redirectUrl;
    } else if (typeof payload.qr_url === 'string' && payload.qr_url) {
      window.open(payload.qr_url);
    }
  }, [
    buildPaymentParams,
    handlePaymentRefreshError,
    isPingxxRedirectChannel,
    isStripeSelected,
    nativePayload,
    orderId,
    payByJsApi,
    payChannel,
    refreshPayment,
    syncOrderStatus,
    t,
  ]);

  const onPayChannelChange = useCallback(
    (value: string) => {
      setPayChannel(value);
      if (!orderId) {
        return;
      }
      void refreshPayment(buildPaymentParams(value, orderId)).catch(
        handlePaymentRefreshError,
      );
    },
    [buildPaymentParams, handlePaymentRefreshError, orderId, refreshPayment],
  );

  const onPayChannelWechatClick = useCallback(() => {
    onPayChannelChange(mobileWechatChannel);
  }, [mobileWechatChannel, onPayChannelChange]);

  const onPayChannelZhifubaoClick = useCallback(() => {
    onPayChannelChange(mobileAlipayChannel);
  }, [mobileAlipayChannel, onPayChannelChange]);

  const onCouponCodeButtonClick = useCallback(() => {
    onCouponCodeModalOpen();
  }, [onCouponCodeModalOpen]);

  const onStripeChannelClick = useCallback(() => {
    onPayChannelChange(PAY_CHANNEL_STRIPE);
  }, [onPayChannelChange]);

  const handleStripeSuccess = useCallback(async () => {
    await syncOrderStatus();
    toast({ title: t('module.pay.paySuccess') });
  }, [syncOrderStatus, t]);

  const handleStripeError = useCallback((message: string) => {
    toast({
      title: message,
      variant: 'destructive',
    });
  }, []);

  const handleStripeCheckout = useCallback(() => {
    if (stripeCheckoutUrl) {
      if (stripePayload.checkout_session_id && orderId) {
        rememberStripeCheckoutSession(
          stripePayload.checkout_session_id,
          orderId,
        );
      }
      window.location.href = stripeCheckoutUrl;
    }
  }, [orderId, stripePayload.checkout_session_id, stripeCheckoutUrl]);

  const onCouponCodeOkClick = useCallback(async () => {
    if (!couponCodeInput) {
      return;
    }
    await applyCoupon({
      code: couponCodeInput,
      ...buildPaymentParams(payChannel, orderId),
    });
    setCouponCodeInput('');
    trackEvent('learner_coupon_apply', {
      shifu_bid: courseId,
      coupon_code: couponCodeInput,
    });
    onCouponCodeModalClose();
  }, [
    applyCoupon,
    buildPaymentParams,
    couponCodeInput,
    courseId,
    onCouponCodeModalClose,
    orderId,
    payChannel,
    trackEvent,
  ]);

  const triggerCancel = useCallback(() => {
    skipNextCancelEventRef.current = true;
    emitCancelEvent();
    onCancel?.();
  }, [emitCancelEvent, onCancel]);

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
    void loadPayInfo();
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
      emitCancelEvent();
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
                                    payChannel === mobileWechatChannel &&
                                      styles.selected,
                                  )}
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
                                    value={mobileWechatChannel}
                                    className={styles.payChannelRadio}
                                  />
                                </div>
                              ) : null}
                              {!isWechatBrowser && alipayPaymentAvailable ? (
                                <div
                                  className={cn(
                                    styles.payChannelRow,
                                    payChannel === mobileAlipayChannel &&
                                      styles.selected,
                                  )}
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
                                    value={mobileAlipayChannel}
                                    className={styles.payChannelRadio}
                                  />
                                </div>
                              ) : null}
                            </RadioGroup>
                          </div>
                        ) : null}
                        {isStripeAvailable ? (
                          <div className={styles.stripeSelector}>
                            <MainButtonM
                              className={cn(
                                styles.stripeButton,
                                isStripeSelected && styles.stripeButtonActive,
                              )}
                              fill={isStripeSelected ? 'solid' : 'none'}
                              onClick={onStripeChannelClick}
                            >
                              {t('module.pay.payChannelStripeCard')}
                            </MainButtonM>
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
                                <MainButtonM
                                  className={styles.payButton}
                                  onClick={handleStripeCheckout}
                                  disabled={!stripeCheckoutUrl}
                                >
                                  {t('module.pay.goToStripeCheckout')}
                                </MainButtonM>
                              </div>
                            ) : (
                              <StripeCardForm
                                clientSecret={stripePayload.client_secret}
                                publishableKey={stripePublishableKey || ''}
                                onConfirmSuccess={handleStripeSuccess}
                                onError={handleStripeError}
                              />
                            )}
                          </div>
                        ) : qrChannelEnabled ? (
                          <div className={styles.buttonWrapper}>
                            <MainButtonM
                              className={styles.payButton}
                              onClick={handlePay}
                              disabled={isLoading}
                            >
                              {t('module.pay.pay')}
                            </MainButtonM>
                          </div>
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
        <Dialog open={couponCodeModalOpen}>
          <DialogContent className={cn('w-5/6', styles.couponCodeModal)}>
            <DialogHeader>
              <DialogTitle>{t('module.groupon.title')}</DialogTitle>
            </DialogHeader>
            <div className={styles.couponCodeInputWrapper}>
              <SettingInputM
                title={t('module.groupon.title')}
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
