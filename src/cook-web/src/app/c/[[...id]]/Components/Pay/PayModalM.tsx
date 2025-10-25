import styles from './PayModalM.module.scss';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';

import Image from 'next/image';
import weixinIcon from '@/c-assets/newchat/weixin.png';
import zhifuboIcon from '@/c-assets/newchat/zhifubao.png';
import payInfoBg from '@/c-assets/newchat/pay-info-bg-m.png';
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
  ORDER_STATUS,
} from './constans';
import MainButtonM from '@/c-components/m/MainButtonM';

import {
  getPayUrl,
  initOrder,
  initActiveOrder,
  applyDiscountCode,
} from '@/c-api/order';
import { useWechat } from '@/c-common/hooks/useWechat';

import { toast } from '@/hooks/useToast';

import { inWechat } from '@/c-constants/uiConstants';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { SettingInputM } from '@/c-components/m/SettingInputM';
import PayModalFooter from './PayModalFooter';

import { getStringEnv } from '@/c-utils/envUtils';
import { useUserStore } from '@/store';
import { shifu } from '@/c-service/Shifu';

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

export const PayModalM = ({
  open = false,
  onCancel,
  onOk,
  type = '',
  payload = {},
}) => {
  const [initLoading, setInitLoading] = useState(true);
  const [price, setPrice] = useState('0.00');
  const [payChannel, setPayChannel] = useState(
    inWechat() ? PAY_CHANNEL_WECHAT_JSAPI : PAY_CHANNEL_ZHIFUBAO,
  );
  const [isCompleted, setIsCompleted] = useState(false);
  const [orderId, setOrderId] = useState('');
  const [couponCode, setCouponCode] = useState('');
  const [originalPrice, setOriginalPrice] = useState('');
  const [priceItems, setPriceItems] = useState([]);

  const { t } = useTranslation();
  const { payByJsApi } = useWechat();

  const {
    open: couponCodeModalOpen,
    onClose: onCouponCodeModalClose,
    onOpen: onCouponCodeModalOpen,
  } = useDisclosure();
  const courseId = getStringEnv('courseId');
  const isLoggedIn = useUserStore(state => state.isLoggedIn);

  const initOrderUniform = useCallback(
    async courseId => {
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
    [payload, type],
  );

  const handlePay = useCallback(async () => {
    const qrcodeResp = await getPayUrl({
      channel: payChannel,
      orderId,
    });

    if (payChannel === PAY_CHANNEL_WECHAT_JSAPI) {
      try {
        await payByJsApi(qrcodeResp.qr_url);
        toast({
          title: t('module.pay.paySuccess'),
        });
        setIsCompleted(true);
        onOk();
      } catch (e) {
        console.log(e);
        toast({
          title: t('module.pay.payFailed'),
          variant: 'destructive',
        });
      }
    } else {
      window.open(qrcodeResp.qr_url);
    }
  }, [onOk, orderId, payByJsApi, payChannel]);

  const onPayChannelChange = useCallback(value => {
    setPayChannel(value);
  }, []);

  const onPayChannelWechatClick = useCallback(() => {
    setPayChannel(PAY_CHANNEL_WECHAT_JSAPI);
  }, []);

  const onPayChannelZhifubaoClick = useCallback(() => {
    setPayChannel(PAY_CHANNEL_ZHIFUBAO);
  }, []);

  const onCouponCodeButtonClick = useCallback(() => {
    onCouponCodeModalOpen();
  }, [onCouponCodeModalOpen]);

  const onCouponCodeOkClick = useCallback(async () => {
    const resp = await applyDiscountCode({ orderId, code: couponCode });

    onCouponCodeModalClose();

    if (resp.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
      setIsCompleted(true);
      onOk();
    }
  }, [couponCode, onCouponCodeModalClose, onOk, orderId]);

  const onLoginButtonClick = useCallback(() => {
    onCancel?.();
    shifu.loginTools.openLogin();
  }, [onCancel]);

  useEffect(() => {
    (async () => {
      const resp = await initOrderUniform(courseId);
      const orderId = resp.order_id;
      setOrderId(orderId);
      setOriginalPrice(resp.price);
      setPrice(resp.value_to_pay);
      setPriceItems(resp.price_item?.filter(item => item.is_discount) || []);
      setInitLoading(false);

      if (resp.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
        setIsCompleted(true);
      }
    })();
  }, [courseId, initOrderUniform]);

  function handleCancel(open: boolean) {
    if (!open) {
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
                {!initLoading ? (
                  <>
                    <div className={styles.payInfoTitle}>
                      {t('module.pay.finalPrice')}
                    </div>
                    <div className={styles.priceWrapper}>
                      <div className={cn(styles.price)}>
                        <span className={styles.priceSign}>￥</span>
                        <span className={styles.priceNumber}>{price}</span>
                      </div>
                    </div>

                    {originalPrice && (
                      <div
                        className={styles.originalPriceWrapper}
                        style={{
                          visibility:
                            originalPrice === price ? 'hidden' : 'visible',
                        }}
                      >
                        <div className={styles.originalPrice}>
                          {originalPrice}
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
                        <div className={styles.payChannelWrapper}>
                          <RadioGroup
                            value={payChannel}
                            onChange={onPayChannelChange}
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
                        <div className={styles.buttonWrapper}>
                          {/* @ts-expect-error EXPECT */}
                          <MainButtonM
                            className={styles.payButton}
                            onClick={handlePay}
                          >
                            {t('module.pay.pay')}
                          </MainButtonM>
                        </div>
                        <div className={styles.couponCodeWrapper}>
                          {/* @ts-expect-error EXPECT */}
                          <MainButtonM
                            className={styles.couponCodeButton}
                            fill='none'
                            onClick={onCouponCodeButtonClick}
                          >
                            {!couponCode
                              ? t('module.groupon.useOtherPayment')
                              : t('module.groupon.modify')}
                          </MainButtonM>
                        </div>
                        <PayModalFooter className={styles.payModalFooter} />
                      </>
                    ) : (
                      <div className={styles.loginButtonWrapper}>
                        {/* @ts-expect-error EXPECT */}
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
              {/* @ts-expect-error EXPECT */}
              <SettingInputM
                title={t('module.groupon.title')}
                onChange={e => setCouponCode(e)}
              />
            </div>
            <div className={styles.buttonWrapper}>
              {/* @ts-expect-error EXPECT */}
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
