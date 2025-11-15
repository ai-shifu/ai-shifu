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
  ORDER_STATUS,
  PAY_CHANNEL_STRIPE,
  PAY_CHANNEL_WECHAT,
} from './constans';
import type { StripePaymentPayload } from '@/c-api/order';

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

  const { stripePublishableKey, stripeEnabled, paymentChannels } = useEnvStore(
    useShallow(state => ({
      stripePublishableKey: state.stripePublishableKey,
      stripeEnabled: state.stripeEnabled,
      paymentChannels: state.paymentChannels,
    })),
  );
  const normalizedPaymentChannels = useMemo(
    () => (paymentChannels || []).map(channel => channel.trim().toLowerCase()),
    [paymentChannels],
  );
  const pingxxChannelEnabled = normalizedPaymentChannels.includes('pingxx');
  const stripeChannelEnabled = normalizedPaymentChannels.includes('stripe');
  const isStripeAvailable =
    stripeChannelEnabled &&
    stripeEnabled === 'true' &&
    Boolean(stripePublishableKey);
  const isStripeSelected = payChannel.startsWith('stripe');
  const stripePayload = (paymentInfo.paymentPayload ||
    {}) as StripePaymentPayload;
  const stripeCheckoutUrl =
    stripePayload.checkout_session_url || paymentInfo.qrUrl || '';
  const stripeMode = (stripePayload.mode || '').toLowerCase();

  const { previewMode } = useSystemStore(
    useShallow(state => ({ previewMode: state.previewMode })),
  );

  const resolveDefaultChannel = useCallback(() => {
    if (pingxxChannelEnabled) {
      return PAY_CHANNEL_WECHAT;
    }
    if (isStripeAvailable) {
      return PAY_CHANNEL_STRIPE;
    }
    return PAY_CHANNEL_WECHAT;
  }, [pingxxChannelEnabled, isStripeAvailable]);

  useEffect(() => {
    const isCurrentSupported =
      (isStripeSelected && isStripeAvailable) ||
      (!isStripeSelected && pingxxChannelEnabled);
    if (isCurrentSupported) {
      return;
    }
    const fallbackChannel = resolveDefaultChannel();
    if (fallbackChannel && fallbackChannel !== payChannel) {
      setPayChannel(fallbackChannel);
      if (orderId) {
        refreshPayment({
          channel: fallbackChannel,
          paymentChannel: fallbackChannel.startsWith('stripe')
            ? 'stripe'
            : undefined,
        });
      }
    }
  }, [
    isStripeSelected,
    isStripeAvailable,
    pingxxChannelEnabled,
    resolveDefaultChannel,
    payChannel,
    orderId,
    refreshPayment,
  ]);

  const loadPayInfo = useCallback(async () => {
    let nextOrderId = orderId;
    if (!nextOrderId) {
      const snapshot = await initializeOrder();
      nextOrderId = snapshot?.order_id || '';
    }
    if (!nextOrderId) {
      return;
    }
    let nextChannel = payChannel;
    if (!pingxxChannelEnabled && isStripeAvailable) {
      nextChannel = PAY_CHANNEL_STRIPE;
      if (nextChannel !== payChannel) {
        setPayChannel(nextChannel);
      }
    }
    await refreshPayment({
      channel: nextChannel,
      paymentChannel: nextChannel.startsWith('stripe') ? 'stripe' : undefined,
    });
  }, [
    initializeOrder,
    isStripeAvailable,
    orderId,
    payChannel,
    pingxxChannelEnabled,
    refreshPayment,
  ]);

  const loadCourseInfo = useCallback(async () => {
    setPreviewLoading(true);
    setPreviewInitLoading(true);
    setPreviewPrice('0');
    try {
      const resp = await getCourseInfo(courseId, previewMode);
      setPreviewPrice(resp?.course_price);
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
      channel: payChannel,
      paymentChannel: payChannel.startsWith('stripe') ? 'stripe' : undefined,
    });
  }, [orderId, payChannel, refreshPayment]);

  let qrcodeStatus = 'active';
  if (effectiveLoading) {
    qrcodeStatus = 'loading';
  } else if (isTimeout) {
    qrcodeStatus = 'expired';
  }

  const onLoginButtonClick = useCallback(() => {
    onCancel?.();
    shifu.loginTools.openLogin();
  }, [onCancel]);

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
        channel: payChannel,
        paymentChannel: payChannel.startsWith('stripe') ? 'stripe' : undefined,
      });
      onCouponCodeModalClose();
    },
    [applyCoupon, onCouponCodeModalClose, payChannel],
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

  const onPayChannelSelectChange = useCallback(
    ({ channel }: { channel: string }) => {
      setPayChannel(channel);
      if (!orderId) {
        return;
      }
      refreshPayment({
        channel,
        paymentChannel: channel.startsWith('stripe') ? 'stripe' : undefined,
      });
    },
    [orderId, refreshPayment],
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
    if (!orderId) {
      initialPaymentRequestedRef.current = false;
    }
  }, [orderId]);

  useEffect(() => {
    if (!open || isLoggedIn) {
      return;
    }
    loadCourseInfo();
  }, [isLoggedIn, loadCourseInfo, open]);

  function handleOpenChange(open: boolean) {
    if (!open) {
      initialPaymentRequestedRef.current = false;
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
                      <span className={styles.priceSign}>￥</span>
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
                        className={`${styles.channelSelectors} ${pingxxChannelEnabled ? styles.pingxxSelected : ''}`}
                      >
                        {pingxxChannelEnabled ? (
                          <div className={styles.channelSwitchWrapper}>
                            <PayChannelSwitch
                              channel={payChannel}
                              onChange={onPayChannelSelectChange}
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
                      ) : pingxxChannelEnabled ? (
                        <div className={cn(styles.qrcodeWrapper, 'relative')}>
                          <QRCodeSVG
                            value={paymentInfo.qrUrl || DEFAULT_QRCODE}
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
                              {qrcodeStatus === 'error' ? (
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
                        {t('module.pay.login')}
                      </Button>
                    </div>
                  )}
                  <PayModalFooter className={styles.payModalFooter} />
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
