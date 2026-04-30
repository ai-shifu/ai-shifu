import styles from './PayModal.module.scss';

import { memo, useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

import Image from 'next/image';
import { LoaderIcon, LoaderCircleIcon } from 'lucide-react';

import { QRCodeSVG } from 'qrcode.react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/Dialog';

import { Button } from '@/components/ui/Button';

import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import CouponCodeModal from './CouponCodeModal';
import {
  PAY_CHANNEL_STRIPE,
  PAY_CHANNEL_WECHAT,
  PAY_CHANNEL_WECHAT_JSAPI,
  PAY_CHANNEL_ZHIFUBAO,
} from './constans';
import type {
  NativePaymentPayload,
  PaymentChannel,
  StripePaymentPayload,
} from '@/c-api/order';

import PayModalFooter from './PayModalFooter';
import PayChannelSwitch from './PayChannelSwitch';
import StripeCardForm from './StripeCardForm';
import { getStringEnv } from '@/c-utils/envUtils';
import { useUserStore } from '@/store';
import { shifu } from '@/c-service/Shifu';
import { getCourseInfo } from '@/c-api/course';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useEnvStore } from '@/c-store/envStore';
import { usePaymentFlow } from './hooks/usePaymentFlow';
import { useToast } from '@/hooks/useToast';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import { useTracking } from '@/c-common/hooks/useTracking';
import { getCurrencyCode } from '@/c-utils/currency';
import { inWechat } from '@/c-constants/uiConstants';

import paySucessBg from '@/c-assets/newchat/pay-success@2x.png';
import payInfoBgCn from '@/c-assets/newchat/pay-info-bg-cn.png';
import payInfoBgEn from '@/c-assets/newchat/pay-info-bg-en.png';

const DEFAULT_QRCODE = 'DEFAULT_QRCODE';

const CompletedSection = memo(() => {
  const { t } = useTranslation();
  return (
    <div className={styles.completedSection}>
      <div className={styles.title}>{t('module.pay.paySuccess')}</div>
      <div className={styles.completeWrapper}>
        <Image
          className={styles.paySuccessBg}
          src={paySucessBg}
          alt=''
        />
      </div>
      <PayModalFooter className={styles.payModalFooter} />
    </div>
  );
});
CompletedSection.displayName = 'CompletedSection';

export const PayModal = ({
  open = false,
  onCancel,
  onOk,
  type = '',
  payload = {},
}) => {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const [payChannel, setPayChannel] = useState(PAY_CHANNEL_WECHAT);
  const [previewPrice, setPreviewPrice] = useState('0');
  const [previewInitLoading, setPreviewInitLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);

  const courseId = getStringEnv('courseId');

  const { isLoggedIn, userInfo } = useUserStore(
    useShallow(state => ({
      isLoggedIn: state.isLoggedIn,
      userInfo: state.userInfo,
    })),
  );

  const {
    orderId,
    price,
    originalPrice,
    priceItems,
    couponCode,
    paymentInfo,
    isLoading,
    initLoading,
    isTimeout,
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
  const effectiveLoading = isLoggedIn ? isLoading : previewLoading;
  const ready = isLoggedIn ? !initLoading : !previewInitLoading;
  const { toast } = useToast();
  const initialPaymentRequestedRef = useRef(false);
  const modalViewTrackedRef = useRef(false);
  const skipNextCancelEventRef = useRef(false);

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
  const isWechatQrAvailable = pingxxChannelEnabled || wechatpayChannelEnabled;
  const isAlipayQrAvailable = pingxxChannelEnabled || alipayChannelEnabled;
  const qrChannelEnabled = isWechatQrAvailable || isAlipayQrAvailable;
  const availableQrChannels = useMemo(() => {
    const channels: string[] = [];
    if (isWechatQrAvailable) {
      channels.push(PAY_CHANNEL_WECHAT);
    }
    if (isAlipayQrAvailable) {
      channels.push(PAY_CHANNEL_ZHIFUBAO);
    }
    return channels;
  }, [isAlipayQrAvailable, isWechatQrAvailable]);
  const isStripeSelected = payChannel.startsWith('stripe');
  const stripePayload = (paymentInfo.paymentPayload ||
    {}) as StripePaymentPayload;
  const nativePayload = (paymentInfo.paymentPayload ||
    {}) as NativePaymentPayload;
  const stripeCheckoutUrl =
    stripePayload.checkout_session_url ||
    (typeof paymentInfo.qrUrl === 'string' ? paymentInfo.qrUrl : '') ||
    '';
  const stripeMode = (stripePayload.mode || '').toLowerCase();
  const isWechatJsapiMode =
    paymentInfo.paymentChannel === 'wechatpay' &&
    nativePayload.mode === 'jsapi' &&
    Boolean(nativePayload.jsapi_params);

  const { previewMode } = useSystemStore(
    useShallow(state => ({ previewMode: state.previewMode })),
  );

  const resolveDefaultChannel = useCallback(() => {
    if (isWechatQrAvailable) {
      return PAY_CHANNEL_WECHAT;
    }
    if (isAlipayQrAvailable) {
      return PAY_CHANNEL_ZHIFUBAO;
    }
    if (isStripeAvailable) {
      return PAY_CHANNEL_STRIPE;
    }
    return PAY_CHANNEL_WECHAT;
  }, [isAlipayQrAvailable, isStripeAvailable, isWechatQrAvailable]);

  const resolveRequestChannel = useCallback(
    (channel: string) => {
      if (
        channel === PAY_CHANNEL_WECHAT &&
        wechatpayChannelEnabled &&
        isWechatBrowser
      ) {
        return PAY_CHANNEL_WECHAT_JSAPI;
      }
      return channel;
    },
    [isWechatBrowser, wechatpayChannelEnabled],
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
      (!isStripeSelected && availableQrChannels.includes(payChannel));
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
    availableQrChannels,
    isStripeSelected,
    isStripeAvailable,
    resolveDefaultChannel,
    resolvePaymentChannel,
    resolveRequestChannel,
    payChannel,
    orderId,
    refreshPayment,
  ]);

  const loadPayInfo = useCallback(async () => {
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
    if (!availableQrChannels.includes(nextChannel) && isStripeAvailable) {
      nextChannel = PAY_CHANNEL_STRIPE;
      if (nextChannel !== payChannel) {
        setPayChannel(nextChannel);
      }
    } else if (!availableQrChannels.includes(nextChannel)) {
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
    availableQrChannels,
    initializeOrder,
    isStripeAvailable,
    orderId,
    payChannel,
    refreshPayment,
    resolveDefaultChannel,
    resolvePaymentChannel,
    resolveRequestChannel,
  ]);

  const loadCourseInfo = useCallback(async () => {
    setPreviewLoading(true);
    setPreviewInitLoading(true);
    setPreviewPrice('0');
    try {
      const resp = await getCourseInfo(courseId, previewMode);
      setPreviewPrice(resp?.course_price);
    } catch {
      // Keep default price for transient course info failures.
    } finally {
      setPreviewLoading(false);
      setPreviewInitLoading(false);
    }
  }, [courseId, previewMode]);

  const onQrcodeRefresh = useCallback(() => {
    if (!orderId) {
      return;
    }
    refreshPayment({
      channel: resolveRequestChannel(payChannel),
      paymentChannel: resolvePaymentChannel(payChannel),
    });
  }, [
    orderId,
    payChannel,
    refreshPayment,
    resolvePaymentChannel,
    resolveRequestChannel,
  ]);

  let qrcodeStatus = 'active';
  if (effectiveLoading) {
    qrcodeStatus = 'loading';
  } else if (isTimeout) {
    qrcodeStatus = 'expired';
  }

  const emitCancelEvent = useCallback(
    (cancelStage: 'modal' | 'payment_page') => {
      trackEvent('learner_pay_cancel', {
        shifu_bid: courseId,
        order_id: orderId || '',
        cancel_stage: cancelStage,
      });
    },
    [courseId, orderId, trackEvent],
  );

  const triggerCancel = useCallback(
    (stage: 'modal' | 'payment_page') => {
      skipNextCancelEventRef.current = true;
      emitCancelEvent(stage);
      onCancel?.();
    },
    [emitCancelEvent, onCancel],
  );

  const onLoginButtonClick = useCallback(() => {
    triggerCancel('modal');
    shifu.loginTools.openLogin();
  }, [triggerCancel]);

  const {
    open: couponCodeModalOpen,
    onOpen: onCouponCodeModalOpen,
    onClose: onCouponCodeModalClose,
  } = useDisclosure();

  const onCouponCodeClick = useCallback(() => {
    onCouponCodeModalOpen();
  }, [onCouponCodeModalOpen]);

  const onCouponCodeOk = useCallback(
    async values => {
      await applyCoupon({
        code: values.couponCode,
        channel: resolveRequestChannel(payChannel),
        paymentChannel: resolvePaymentChannel(payChannel),
      });
      trackEvent('learner_coupon_apply', {
        shifu_bid: courseId,
        coupon_code: values.couponCode,
      });
      onCouponCodeModalClose();
    },
    [
      applyCoupon,
      courseId,
      onCouponCodeModalClose,
      payChannel,
      resolvePaymentChannel,
      resolveRequestChannel,
      trackEvent,
    ],
  );

  const handleStripeSuccess = useCallback(async () => {
    await syncOrderStatus();
    toast({ title: t('module.pay.paySuccess') });
  }, [syncOrderStatus, t, toast]);

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

  const handleStripeError = useCallback(
    (message: string) => {
      toast({
        title: message,
        variant: 'destructive',
      });
    },
    [toast],
  );

  const handleWechatJsapiPay = useCallback(async () => {
    const jsapiParams = nativePayload.jsapi_params;
    if (!jsapiParams || typeof window === 'undefined') {
      return;
    }
    if (!isWechatBrowser) {
      toast({
        title: t('module.pay.wechatJsapiUnavailable'),
        variant: 'destructive',
      });
      return;
    }

    try {
      await new Promise<void>((resolve, reject) => {
        const invokePayment = () => {
          const bridge = (
            window as typeof window & {
              WeixinJSBridge?: {
                invoke: (
                  name: string,
                  params: Record<string, string>,
                  callback: (result: { err_msg?: string }) => void,
                ) => void;
              };
            }
          ).WeixinJSBridge;
          if (!bridge) {
            reject(new Error('wechat_bridge_unavailable'));
            return;
          }
          bridge.invoke(
            'getBrandWCPayRequest',
            jsapiParams,
            (result: { err_msg?: string }) => {
              if (result.err_msg === 'get_brand_wcpay_request:ok') {
                resolve();
                return;
              }
              reject(new Error(result.err_msg || 'wechat_pay_failed'));
            },
          );
        };

        const bridge = (window as typeof window & { WeixinJSBridge?: unknown })
          .WeixinJSBridge;
        if (bridge) {
          invokePayment();
          return;
        }
        document.addEventListener('WeixinJSBridgeReady', invokePayment, {
          once: true,
        });
      });
      try {
        await syncOrderStatus({ paymentChannel: 'wechatpay' });
      } catch {
        // The polling loop continues syncing native payments after the bridge reports success.
      }
      toast({ title: t('module.pay.paySuccess') });
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('WeChat JSAPI payment failed', error);
      toast({
        title:
          error instanceof Error &&
          error.message === 'wechat_bridge_unavailable'
            ? t('module.pay.wechatJsapiUnavailable')
            : t('module.pay.payFailed'),
        variant: 'destructive',
      });
    }
  }, [isWechatBrowser, nativePayload.jsapi_params, syncOrderStatus, t, toast]);

  const onPayChannelSelectChange = useCallback(
    ({ channel }: { channel: string }) => {
      setPayChannel(channel);
      if (!orderId) {
        return;
      }
      refreshPayment({
        channel: resolveRequestChannel(channel),
        paymentChannel: resolvePaymentChannel(channel),
      });
    },
    [orderId, refreshPayment, resolvePaymentChannel, resolveRequestChannel],
  );

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
    if (!orderId && !initLoading && !isLoading) {
      // Only release the one-shot guard after the current payment bootstrap settles.
      initialPaymentRequestedRef.current = false;
    }
  }, [initLoading, isLoading, orderId]);

  const currencyCode = useMemo(
    () => getCurrencyCode(currencySymbol),
    [currencySymbol],
  );

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

  useEffect(() => {
    if (!open || isLoggedIn) {
      return;
    }
    loadCourseInfo();
  }, [isLoggedIn, loadCourseInfo, open]);

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      initialPaymentRequestedRef.current = false;
      if (skipNextCancelEventRef.current) {
        skipNextCancelEventRef.current = false;
        return;
      }
      emitCancelEvent('modal');
      onCancel?.();
    }
  }

  const payInfoBg = userInfo?.language === 'en-US' ? payInfoBgEn : payInfoBgCn;

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={handleOpenChange}
      >
        <DialogContent
          className={cn(styles.payModal, 'max-w-none')}
          onPointerDownOutside={evt => evt.preventDefault()}
        >
          <DialogTitle className='sr-only'>
            {t('module.pay.dialogTitle')}
          </DialogTitle>
          {ready && (
            <div className={styles.payModalContent}>
              <div
                className={styles.introSection}
                style={{ backgroundImage: `url(${payInfoBg.src})` }}
              ></div>
              {isCompleted ? (
                <CompletedSection />
              ) : (
                <div className={styles.paySection}>
                  <div className={styles.payInfoTitle}>
                    {t('module.pay.finalPrice')}
                  </div>
                  <div className={styles.priceWrapper}>
                    <div
                      className={cn(
                        styles.price,
                        (effectiveLoading || isTimeout) && styles.disabled,
                      )}
                    >
                      <span className={styles.priceSign}>{currencySymbol}</span>
                      <span className={styles.priceNumber}>{displayPrice}</span>
                    </div>
                  </div>
                  {displayOriginalPrice && (
                    <div
                      className={styles.originalPriceWrapper}
                      style={{
                        display:
                          displayOriginalPrice === displayPrice
                            ? 'none'
                            : 'block',
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
                      <div
                        className={`${styles.channelSelectors} ${qrChannelEnabled ? styles.pingxxSelected : ''}`}
                      >
                        {qrChannelEnabled ? (
                          <div className={styles.channelSwitchWrapper}>
                            <PayChannelSwitch
                              channel={payChannel}
                              onChange={onPayChannelSelectChange}
                              availableChannels={availableQrChannels}
                            />
                          </div>
                        ) : null}
                        {isStripeAvailable ? (
                          <div className={styles.stripeSelector}>
                            <div
                              onClick={() =>
                                onPayChannelSelectChange({
                                  channel: PAY_CHANNEL_STRIPE,
                                })
                              }
                            >
                              {t('module.pay.payChannelStripeCard')}
                            </div>
                          </div>
                        ) : null}
                      </div>
                      {isStripeSelected ? (
                        <div className={styles.stripePanel}>
                          {stripeMode === 'checkout_session' ||
                          !stripePayload.client_secret ? (
                            <div className='space-y-3 text-center'>
                              <p className={styles.stripeHint}>
                                {t('module.pay.stripeCheckoutHint')}
                              </p>
                              <Button
                                className={styles.stripeCheckoutButton}
                                onClick={handleStripeCheckout}
                                disabled={!stripeCheckoutUrl}
                              >
                                {t('module.pay.goToStripeCheckout')}
                              </Button>
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
                        isWechatJsapiMode ? (
                          <div className='space-y-3 text-center'>
                            <p className={styles.stripeHint}>
                              {t('module.pay.wechatJsapiHint')}
                            </p>
                            <Button
                              className={styles.stripeCheckoutButton}
                              onClick={handleWechatJsapiPay}
                              disabled={effectiveLoading}
                            >
                              {t('module.pay.wechatJsapiPay')}
                            </Button>
                          </div>
                        ) : (
                          <div className={cn(styles.qrcodeWrapper, 'relative')}>
                            <QRCodeSVG
                              value={
                                (typeof paymentInfo.qrUrl === 'string'
                                  ? paymentInfo.qrUrl
                                  : '') || DEFAULT_QRCODE
                              }
                              size={175}
                              level={'M'}
                            />
                            {qrcodeStatus !== 'active' ? (
                              <div className='absolute left-0 top-0 right-0 bottom-0 flex flex-col items-center justify-center pointer-events-none bg-white/50 backdrop-blur-[1px] transition-opacity duration-200'>
                                {qrcodeStatus === 'loading' ? (
                                  <LoaderIcon
                                    className={cn(
                                      'animation-spin h-8 w-8 drop-shadow',
                                      styles.price,
                                    )}
                                  />
                                ) : null}
                                {qrcodeStatus === 'expired' ? (
                                  <Button
                                    className='pointer-events-auto bg-white/95 text-black shadow'
                                    variant='outline'
                                    onClick={onQrcodeRefresh}
                                  >
                                    <LoaderCircleIcon />
                                    {t('module.pay.clickRefresh')}
                                  </Button>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        )
                      ) : (
                        <div className={styles.stripeHint}>
                          {t('module.pay.stripeError')}
                        </div>
                      )}
                      <div className={styles.couponCodeWrapper}>
                        <Button
                          variant='link'
                          onClick={onCouponCodeClick}
                          className={styles.couponCodeButton}
                        >
                          {!couponCode
                            ? t('module.groupon.useOtherPayment')
                            : t('module.groupon.modify')}
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className={styles.loginButtonWrapper}>
                      <Button onClick={onLoginButtonClick}>
                        {t('module.auth.login')}
                      </Button>
                    </div>
                  )}
                  <PayModalFooter
                    className={cn(
                      styles.payModalFooter,
                      priceItems && priceItems.length > 0
                        ? 'hasPriceItems'
                        : '',
                    )}
                  />
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {couponCodeModalOpen ? (
        <CouponCodeModal
          open={couponCodeModalOpen}
          onCancel={onCouponCodeModalClose}
          onOk={onCouponCodeOk}
        />
      ) : null}
    </>
  );
};

export default memo(PayModal);
