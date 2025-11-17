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
  PAY_CHANNEL_WECHAT_JSAPI,
  PAY_CHANNEL_ZHIFUBAO,
  PAY_CHANNEL_STRIPE,
  ORDER_STATUS,
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
import type { StripePaymentPayload } from '@/c-api/order';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import { getCourseInfo } from '@/c-api/course';
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

const pingxxDefaultChannel = inWechat()
  ? PAY_CHANNEL_WECHAT_JSAPI
  : PAY_CHANNEL_ZHIFUBAO;

export const PayModalM = ({
  open = false,
  onCancel,
  onOk,
  type = '',
  payload = {},
}) => {
  const [payChannel, setPayChannel] = useState(pingxxDefaultChannel);
  const [couponCodeInput, setCouponCodeInput] = useState('');
  const [previewPrice, setPreviewPrice] = useState('0');
  const [previewInitLoading, setPreviewInitLoading] = useState(true);

  const courseId = getStringEnv('courseId');
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const { t } = useTranslation();
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
  const stripePayload = (paymentInfo?.paymentPayload ||
    {}) as StripePaymentPayload;
  const stripeCheckoutUrl =
    stripePayload.checkout_session_url || paymentInfo?.qrUrl || '';
  const stripeMode = (stripePayload.mode || '').toLowerCase();

  const resolveDefaultChannel = useCallback(() => {
    if (pingxxChannelEnabled) {
      return pingxxDefaultChannel;
    }
    if (isStripeAvailable) {
      return PAY_CHANNEL_STRIPE;
    }
    return pingxxDefaultChannel;
  }, [pingxxChannelEnabled, isStripeAvailable, pingxxDefaultChannel]);

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
    if (!isLoggedIn) {
      return;
    }
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
    isLoggedIn,
    isStripeAvailable,
    orderId,
    payChannel,
    pingxxChannelEnabled,
    refreshPayment,
  ]);

  const loadCourseInfo = useCallback(async () => {
    setPreviewInitLoading(true);
    try {
      const resp = await getCourseInfo(courseId, previewMode);
      setPreviewPrice(resp?.course_price);
    } finally {
      setPreviewInitLoading(false);
    }
  }, [courseId, previewMode]);

  const handlePay = useCallback(async () => {
    if (isStripeSelected) {
      return;
    }
    const payload = await refreshPayment({ channel: payChannel });
    if (!payload) {
      return;
    }

    if (payChannel === PAY_CHANNEL_WECHAT_JSAPI) {
      try {
        await payByJsApi(payload.qr_url);
        toast({
          title: t('module.pay.paySuccess'),
        });
        onOk();
      } catch {
        toast({
          title: t('module.pay.payFailed'),
          variant: 'destructive',
        });
      }
    } else {
      window.open(payload.qr_url);
    }
  }, [isStripeSelected, onOk, payByJsApi, payChannel, refreshPayment, t]);

  const onPayChannelChange = useCallback(
    (value: string) => {
      setPayChannel(value);
      if (!orderId) {
        return;
      }
      refreshPayment({
        channel: value,
        paymentChannel: value.startsWith('stripe') ? 'stripe' : undefined,
      });
    },
    [orderId, refreshPayment],
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
      channel: payChannel,
      paymentChannel: payChannel.startsWith('stripe') ? 'stripe' : undefined,
    });
    setCouponCodeInput('');
    onCouponCodeModalClose();
  }, [applyCoupon, couponCodeInput, onCouponCodeModalClose, payChannel]);

  const onLoginButtonClick = useCallback(() => {
    onCancel?.();
    shifu.loginTools.openLogin();
  }, [onCancel]);

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

  function handleCancel(open: boolean) {
    if (!open) {
      initialPaymentRequestedRef.current = false;
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
                        {pingxxChannelEnabled ? (
                          <div className={styles.payChannelWrapper}>
                            <RadioGroup
                              value={payChannel}
                              onValueChange={onPayChannelChange}
                            >
                              {inWechat() && (
                                <div
                                  className={cn(
                                    styles.payChannelRow,
                                    payChannel === PAY_CHANNEL_WECHAT_JSAPI &&
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
                                    value={PAY_CHANNEL_WECHAT_JSAPI}
                                    className={styles.payChannelRadio}
                                  />
                                </div>
                              )}
                              {!inWechat() && (
                                <div
                                  className={cn(
                                    styles.payChannelRow,
                                    payChannel === PAY_CHANNEL_ZHIFUBAO &&
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
                                    value={PAY_CHANNEL_ZHIFUBAO}
                                    className={styles.payChannelRadio}
                                  />
                                </div>
                              )}
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
                        ) : pingxxChannelEnabled ? (
                          <div className={styles.buttonWrapper}>
                            <MainButtonM
                              className={styles.payButton}
                              onClick={handlePay}
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
