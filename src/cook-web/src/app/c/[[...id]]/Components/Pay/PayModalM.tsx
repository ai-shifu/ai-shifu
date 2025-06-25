import styles from './PayModalM.module.scss';

import { memo, useState, useCallback, useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils'

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
} from "@/components/ui/dialog"
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';

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

import { toast } from '@/hooks/use-toast';

import { inWechat } from '@/c-constants/uiConstants';
import { useDisclosture } from '@/c-common/hooks/useDisclosture';
import { SettingInputM } from '@/c-components/m/SettingInputM';
import PayModalFooter from './PayModalFooter';

import { getStringEnv } from '@/c-utils/envUtils';
import { useUserStore } from '@/c-store/useUserStore';
import { shifu } from '@/c-service/Shifu';

const CompletedSection = memo(() => {
  const { t } = useTranslation('translation', { keyPrefix: 'c'});
  return (
    <div className={styles.completedSection}>
      <div className={styles.title}>{t('pay.paySuccess')}</div>
      <div className={styles.completeWrapper}>
        <Image className={styles.paySuccessBg} src={paySuccessBg.src} alt="pay-success-bg" />
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
    inWechat() ? PAY_CHANNEL_WECHAT_JSAPI : PAY_CHANNEL_ZHIFUBAO
  );
  const [isCompleted, setIsCompleted] = useState(false);
  const [orderId, setOrderId] = useState('');
  const [couponCode, setCouponCode] = useState('');
  const [originalPrice, setOriginalPrice] = useState('');
  const [priceItems, setPriceItems] = useState([]);

  const { t } = useTranslation('translation', { keyPrefix: 'c'});
  const { payByJsApi } = useWechat();

  const {
    open: couponCodeModalOpen,
    onClose: onCouponCodeModalClose,
    onOpen: onCouponCodeModalOpen,
  } = useDisclosture();
  const courseId = getStringEnv('courseId');
  const { hasLogin } = useUserStore(
    useShallow((state) => ({ hasLogin: state.hasLogin }))
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

  const handlePay = useCallback(async () => {
    const { data: qrcodeResp } = await getPayUrl({
      channel: payChannel,
      orderId,
    });

    if (payChannel === PAY_CHANNEL_WECHAT_JSAPI) {
      try {
        await payByJsApi(qrcodeResp.qr_url);
        toast({
          title: '支付成功',
        })
        setIsCompleted(true);
        onOk();
      } catch (e) {
        console.log(e)
        toast({
          title: '支付失败',
          variant: 'destructive',
        });
      }
    } else {
      window.open(qrcodeResp.qr_url);
    }
  }, [ onOk, orderId, payByJsApi, payChannel]);

  const onPayChannelChange = useCallback((value) => {
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
    // @ts-expect-error EXPECT
    if (resp.code !== 0) {
      toast({
        // @ts-expect-error EXPECT
        title: resp.message,
        variant: 'destructive',
      })
      return;
    }

    onCouponCodeModalClose();

    if (resp.data.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
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
      const { data: resp } = await initOrderUniform(courseId);
      const orderId = resp.order_id;
      setOrderId(orderId);
      setOriginalPrice(resp.price);
      setPrice(resp.value_to_pay);
      setPriceItems(resp.price_item?.filter((item) => item.is_discount) || []);
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
      <Dialog open={open} onOpenChange={handleCancel}>
        <DialogContent className="w-full">
          <div className={styles.payModalContent}>
            {isCompleted ? (
              <CompletedSection />
            ) : (
              <>
                {!initLoading ? (
                  <>
                    <div className={styles.payInfoTitle}>到手价格</div>
                    <div className={styles.priceWrapper}>
                      <div className={cn(styles.price)}>
                        <span className={styles.priceSign}>￥</span>
                        <span className={styles.priceNumber}>{price}</span>
                      </div>
                    </div>

                    {originalPrice && (
                      <div className={styles.originalPriceWrapper} style={{ visibility: originalPrice === price ? 'hidden' : 'visible' }}>
                        <div className={styles.originalPrice}>
                          {originalPrice}
                        </div>
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
                    {hasLogin ? (
                      <>
                        <div className={styles.payChannelWrapper}>
                          <RadioGroup
                            value={payChannel}
                            onChange={onPayChannelChange}>
                            {inWechat() && (
                              <div
                                className={cn(
                                  styles.payChannelRow,
                                  payChannel === PAY_CHANNEL_WECHAT_JSAPI &&
                                    styles.selected
                                )}
                                onClick={onPayChannelWechatClick}
                              >
                                <div className={styles.payChannelBasic}>
                                  <Image className={styles.payChannelIcon} src={weixinIcon.src} alt="微信支付" />
                                  <span className={styles.payChannelTitle}>
                                    微信支付
                                  </span>
                                </div>
                                <RadioGroupItem value={PAY_CHANNEL_WECHAT_JSAPI} className={styles.payChannelRadio} />
                              </div>
                            )}
                            {!inWechat() && (
                              <div
                                className={cn(
                                  styles.payChannelRow,
                                  payChannel === PAY_CHANNEL_ZHIFUBAO &&
                                    styles.selected
                                )}
                                onClick={onPayChannelZhifubaoClick}
                              >
                                <div className={styles.payChannelBasic}>
                                  <Image className={styles.payChannelIcon} src={zhifuboIcon.src} alt="支付宝支付" />
                                  <span className={styles.payChannelTitle}>
                                    支付宝支付
                                  </span>
                                </div>
                                <RadioGroupItem value={PAY_CHANNEL_ZHIFUBAO} className={styles.payChannelRadio} />
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
                            支付
                          </MainButtonM>
                        </div>
                        <div className={styles.couponCodeWrapper}>
                          {/* @ts-expect-error EXPECT */}
                          <MainButtonM
                            className={styles.couponCodeButton}
                            fill="none"
                            onClick={onCouponCodeButtonClick}
                          >
                            {!couponCode
                              ? t('groupon.grouponUse')
                              : t('groupon.grouponModify')}
                          </MainButtonM>
                        </div>
                        <PayModalFooter className={styles.payModalFooter} />
                      </>
                    ) : (
                      <div className={styles.loginButtonWrapper}>
                        {/* @ts-expect-error EXPECT */}
                        <MainButtonM onClick={onLoginButtonClick}>
                          登录
                        </MainButtonM>
                      </div>
                    )}
                  </>
                ) : (
                  <></>
                )}
              </>
            )}

            <div className={styles.payInfoWrapper}>
              <Image className={styles.payInfo} src={payInfoBg.src} alt="产品说明" />
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {couponCodeModalOpen && (
        <Dialog open={couponCodeModalOpen}>
          <DialogContent className={cn('w-5/6', styles.couponCodeModal)}>
            <DialogHeader>
              <DialogTitle>兑换码</DialogTitle>
            </DialogHeader>
              <div className={styles.couponCodeInputWrapper}>
                {/* @ts-expect-error EXPECT */}
                <SettingInputM
                  title="兑换码"
                  onChange={(e) => setCouponCode(e)}
                />
              </div>
              <div className={styles.buttonWrapper}>
                {/* @ts-expect-error EXPECT */}
                <MainButtonM
                  onClick={onCouponCodeOkClick}
                  className={styles.okButton}>
                  确定
                </MainButtonM>
              </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
};

export default memo(PayModalM);
