import styles from './PayModal.module.scss';

import { memo, useState, useCallback, useEffect } from 'react';
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
import { ORDER_STATUS, PAY_CHANNEL_WECHAT } from './constans';

import PayModalFooter from './PayModalFooter';
import PayChannelSwitch from './PayChannelSwitch';
import { getStringEnv } from '@/c-utils/envUtils';
import { useUserStore } from '@/store';
import { shifu } from '@/c-service/Shifu';
import { getCourseInfo } from '@/c-api/course';
import { useSystemStore } from '@/c-store/useSystemStore';
import { usePaymentFlow } from './hooks/usePaymentFlow';

import paySucessBg from '@/c-assets/newchat/pay-success@2x.png';
import payInfoBg from '@/c-assets/newchat/pay-info-bg.png';

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
      <PayModalFooter />
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

  const {
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

  const isLoggedIn = useUserStore(state => state.isLoggedIn);

  const { previewMode } = useSystemStore(
    useShallow(state => ({ previewMode: state.previewMode })),
  );

  const loadPayInfo = useCallback(async () => {
    const snapshot = await initializeOrder();
    if (
      snapshot &&
      (snapshot.status === ORDER_STATUS.BUY_STATUS_INIT ||
        snapshot.status === ORDER_STATUS.BUY_STATUS_TO_BE_PAID)
    ) {
      await refreshPayment({ channel: payChannel });
    }
  }, [initializeOrder, payChannel, refreshPayment]);

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
    loadPayInfo();
  }, [loadPayInfo]);

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
      });
      onCouponCodeModalClose();
    },
    [applyCoupon, onCouponCodeModalClose, payChannel],
  );

  const onPayChannelSelectChange = useCallback(e => {
    setPayChannel(e.channel);
  }, []);

  useEffect(() => {
    if (!open || !isLoggedIn) {
      return;
    }
    loadPayInfo();
  }, [isLoggedIn, loadPayInfo, open]);

  useEffect(() => {
    if (!open || isLoggedIn) {
      return;
    }
    loadCourseInfo();
  }, [isLoggedIn, loadCourseInfo, open]);

  function handleOpenChange(open: boolean) {
    if (!open) {
      onCancel?.();
    }
  }

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
                  <div className={styles.payInfoTitle}>到手价格</div>
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
                              {/* @ts-expect-error EXPECT */}
                              {item.price_name}
                            </div>
                            <div className={styles.priceItemPrice}>
                              {/* @ts-expect-error EXPECT */}
                              {item.price}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {isLoggedIn ? (
                    <>
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
                                点击刷新
                              </Button>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                      <div className={styles.channelSwitchWrapper}>
                        <PayChannelSwitch
                          channel={payChannel}
                          // @ts-expect-error EXPECT
                          onChange={onPayChannelSelectChange}
                        />
                      </div>
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
                      <Button onClick={onLoginButtonClick}>登录</Button>
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
