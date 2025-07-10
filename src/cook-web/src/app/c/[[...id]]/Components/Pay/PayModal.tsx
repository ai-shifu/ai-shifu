import styles from './PayModal.module.scss';

import { memo, useState, useCallback, useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils'

import Image from 'next/image';
import { LoaderIcon, LoaderCircleIcon } from 'lucide-react'

import { QRCodeSVG } from 'qrcode.react';
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog"

import { Button } from '@/components/ui/button';

import { toast } from '@/hooks/use-toast';

import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import CouponCodeModal from './CouponCodeModal';
import { ORDER_STATUS, PAY_CHANNEL_WECHAT } from './constans';
import {
  getPayUrl,
  initOrder,
  initActiveOrder,
  queryOrder,
  applyDiscountCode,
} from '@/c-api/order';

import PayModalFooter from './PayModalFooter';
import PayChannelSwitch from './PayChannelSwitch';
import { getStringEnv } from '@/c-utils/envUtils';
import { useUserStore } from '@/c-store/useUserStore';
import { shifu } from '@/c-service/Shifu';
import { getCourseInfo } from '@/c-api/course';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useInterval } from 'react-use';

import paySucessBg from '@/c-assets/newchat/pay-success@2x.png';
import payInfoBg from '@/c-assets/newchat/pay-info-bg.png';

const DEFAULT_QRCODE = 'DEFAULT_QRCODE';
const MAX_TIMEOUT = 1000 * 60 * 3;
const COUNTDOWN_INTERVAL = 1000;

const CompletedSection = memo(() => {
  const { t } = useTranslation('translation', { keyPrefix: 'c'});
  return (
    <div className={styles.completedSection}>
      <div className={styles.title}>{t('pay.paySuccess')}</div>
      <div className={styles.completeWrapper}>
        <Image className={styles.paySuccessBg} src={paySucessBg.src} alt="" />
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
  const { t } = useTranslation('translation', {keyPrefix: 'c'});
  const [isLoading, setIsLoading] = useState(false);
  const [initLoading, setInitLoading] = useState(true);
  const [isTimeout, setIsTimeout] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);

  const [price, setPrice] = useState('');
  const [qrUrl, setQrUrl] = useState(DEFAULT_QRCODE);
  const [payChannel, setPayChannel] = useState(PAY_CHANNEL_WECHAT);
  const [interval, setInterval] = useState(null);
  const [orderId, setOrderId] = useState('');
  const [countDwon, setCountDown] = useState(MAX_TIMEOUT);

  const [couponCode, setCouponCode] = useState('');
  const [originalPrice, setOriginalPrice] = useState('');
  const [priceItems, setPriceItems] = useState([]);

  const isLoggedIn = useUserStore((state) => state.isLoggedIn);

  const { previewMode } = useSystemStore(
    useShallow((state) => ({ previewMode: state.previewMode }))
  );

  const initOrderUniform = useCallback(
    async (courseId) => {
      if (type === 'active') {
        // @ts-expect-error EXPECT
        return initActiveOrder({
          courseId,
          ...payload,
        });
      } else {
        return initOrder(courseId);
      }
    },
    [payload, type]
  );

  useInterval(
    async () => {
      if (countDwon <= 0) {
        setIsTimeout(true);
        setInterval(null);
      }
      setCountDown(countDwon - COUNTDOWN_INTERVAL);

      const { data: resp } = await queryOrder({ orderId });

      if (resp.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
        setIsCompleted(true);
        setInterval(null);
        onOk?.();
        return;
      }

      setOriginalPrice(resp.price);
      setPriceItems(resp.price_item?.filter((item) => item.is_discount) || []);
      setPrice(resp.value_to_pay);
    },
    isLoggedIn ? interval : null
  );

  const refreshOrderQrcode = useCallback(
    async (orderId) => {
      if (orderId) {
        const { data: qrcodeResp } = await getPayUrl({
          channel: payChannel,
          orderId,
        });
        setQrUrl(qrcodeResp.qr_url);
        if (qrcodeResp.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
          setIsCompleted(true);
          setInterval(null);
        } else {
          setCountDown(MAX_TIMEOUT);
          // @ts-expect-error EXPECT
          setInterval(COUNTDOWN_INTERVAL);
        }
      }
    },
    [payChannel]
  );

  const courseId = getStringEnv('courseId');
  const loadPayInfo = useCallback(async () => {
    setIsLoading(true);
    setIsTimeout(false);
    setQrUrl(DEFAULT_QRCODE);
    setPrice('0');
    setOrderId('');
    setInterval(null);
    setCouponCode('');
    setOriginalPrice('');
    const { data: resp } = await initOrderUniform(courseId);
    setPrice(resp.value_to_pay);
    setPriceItems(resp.price_item?.filter((item) => item.is_discount) || []);
    const orderId = resp.order_id;
    setOrderId(orderId);
    setOriginalPrice(resp.price);

    if (
      resp.status === ORDER_STATUS.BUY_STATUS_INIT ||
      resp.status === ORDER_STATUS.BUY_STATUS_TO_BE_PAID
    ) {
      await refreshOrderQrcode(orderId);
    }

    if (resp.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
      setIsCompleted(true);
    }

    setIsLoading(false);
  }, [courseId, initOrderUniform, refreshOrderQrcode]);

  const loadCourseInfo = useCallback(async () => {
    setIsLoading(true);
    setIsTimeout(false);
    setQrUrl(DEFAULT_QRCODE);
    setPrice('0');
    setOrderId('');
    setInterval(null);
    setCouponCode('');
    setOriginalPrice('');

    const resp = await getCourseInfo(courseId, previewMode);
    setPrice(resp.data.course_price);

    setIsLoading(false);
  }, [courseId, previewMode]);

  const onQrcodeRefresh = useCallback(() => {
    loadPayInfo();
  }, [loadPayInfo]);

  let qrcodeStatus = 'active';
  if (isLoading) {
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
    async (values) => {
      const { couponCode } = values;
      setCouponCode(couponCode);
      const resp = await applyDiscountCode({ orderId, code: couponCode });
      // @ts-expect-error EXPECT
      if (resp.code !== 0) {
        toast({
          // @ts-expect-error EXPECT
          title: resp.message,
          variant: 'destructive',
        })
        return;
      }
      refreshOrderQrcode(resp.data.order_id);
      onCouponCodeModalClose();
    },
    [ onCouponCodeModalClose, orderId, refreshOrderQrcode]
  );

  const onPayChannelSelectChange = useCallback((e) => {
    setPayChannel(e.channel);
  }, []);

  useEffect(() => {
    if (!open || !isLoggedIn) {
      return;
    }
    loadPayInfo();
    setInitLoading(false);
  }, [isLoggedIn, loadPayInfo, open]);

  useEffect(() => {
    if (!isLoggedIn) {
      loadCourseInfo();
      setInitLoading(false);
    }
  }, [isLoggedIn, loadCourseInfo]);

  function handleOpenChange(open: boolean) {
    if (!open) {
      onCancel?.();
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent 
        className={cn(styles.payModal, 'w-[700px] h-[588px]')}
        onPointerDownOutside={(evt) => evt.preventDefault()}>
          {!initLoading && (
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
                        (isLoading || isTimeout) && styles.disabled
                      )}
                    >
                      <span className={styles.priceSign}>￥</span>
                      <span className={styles.priceNumber}>{price}</span>
                    </div>
                  </div>
                  {originalPrice && (
                    <div className={styles.originalPriceWrapper} style={{ visibility: originalPrice === price ? 'hidden' : 'visible' }}>
                      <div className={styles.originalPrice}>{originalPrice}</div>
                    </div>
                  )}
                  {priceItems && priceItems.length > 0 && (
                    <div className={styles.priceItemsWrapper}>
                      {priceItems.map((item, index) => {
                        return (
                          <div className={styles.priceItem} key={index}>
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
                          value={qrUrl}
                          size={175}
                          level={'M'}
                        />
                        {qrcodeStatus !== 'active' ? (
                          <div className='absolute left-0 top-0 right-0 bottom-0 flex flex-col content-center justify-center bg-black/75'>
                            {qrcodeStatus === 'loading' ? (
                              <LoaderIcon className='animation-spin' />
                            ) : null}
                            {qrcodeStatus === 'error' ? (
                              <Button variant="outline" onClick={onQrcodeRefresh}>
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
                          variant="link"
                          onClick={onCouponCodeClick}
                          className={styles.couponCodeButton}
                        >
                          {!couponCode
                            ? t('groupon.grouponUse')
                            : t('groupon.grouponModify')}
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className={styles.loginButtonWrapper}>
                      <Button onClick={onLoginButtonClick}>
                        登录
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
