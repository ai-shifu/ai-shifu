import { memo, useState, useCallback, useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';
import ModalM from 'Components/m/ModalM';
import styles from './PayModalM.module.scss';
import classNames from 'classnames';

import weixinIcon from 'Assets/newchat/weixin.png';
import zhifuboIcon from 'Assets/newchat/zhifubao.png';

import RadioM from 'Components/m/RadioM';
import { Radio } from 'antd-mobile';
import {
  PAY_CHANNEL_WECHAT_JSAPI,
  PAY_CHANNEL_ZHIFUBAO,
  ORDER_STATUS,
} from './constans';
import MainButtonM from 'Components/m/MainButtonM';
import payInfoBg from 'Assets/newchat/pay-info-bg-m.png';

import {
  getPayUrl,
  initOrder,
  initActiveOrder,
  applyDiscountCode,
} from 'Api/order';
import { useWechat } from 'common/hooks/useWechat';
import { message } from 'antd';
import { inWechat } from 'constants/uiConstants';
import { useDisclosture } from 'common/hooks/useDisclosture';
import { SettingInputM } from 'Components/m/SettingInputM';
import PayModalFooter from './PayModalFooter';
import paySuccessBg from 'Assets/newchat/pay-success@2x.png';
import { getStringEnv } from 'Utils/envUtils';
import { useUserStore } from 'stores/useUserStore';
import { shifu } from 'Service/Shifu';

const CompletedSection = memo(() => {
  const { t } = useTranslation();
  return (
    <div className={styles.completedSection}>
      <div className={styles.title}>{t('pay.paySuccess')}</div>
      <div className={styles.completeWrapper}>
        <img className={styles.paySuccessBg} src={paySuccessBg} alt="" />
      </div>
      <PayModalFooter />
    </div>
  );
});

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
  const [messageApi, contextHolder] = message.useMessage();
  const {
    open: couponCodeModalOpen,
    onClose: onCouponCodeModalClose,
    onOpen: onCouponCodeModalOpen,
  } = useDisclosture();
  const courseId = getStringEnv('courseId');
  const { hasLogin } = useUserStore(
    useShallow((state) => ({ hasLogin: state.hasLogin })),
  );

  const initOrderUniform = useCallback(
    async (courseId) => {
      if (type === 'active') {
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
    const { data: qrcodeResp } = await getPayUrl({
      channel: payChannel,
      orderId,
    });

    if (payChannel === PAY_CHANNEL_WECHAT_JSAPI) {
      try {
        await payByJsApi(qrcodeResp.qr_url);
        messageApi.success('支付成功');
        setIsCompleted(true);
        onOk();
      } catch (e) {
        messageApi.error('支付失败');
      }
    } else {
      window.open(qrcodeResp.qr_url);
    }
  }, [messageApi, onOk, orderId, payByJsApi, payChannel]);

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
    if (resp.code !== 0) {
      messageApi.error(resp.message);
      return;
    }

    onCouponCodeModalClose();

    if (resp.data.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
      setIsCompleted(true);
      onOk();
    }
  }, [couponCode, messageApi, onCouponCodeModalClose, onOk, orderId]);

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

  return (
    <>
      <ModalM
        className={''}
        visible={open}
        onClose={onCancel}
        style={{ wdith: '100%' }}
        content={
          <div className={styles.payModalContent}>
            {isCompleted ? (
              <CompletedSection />
            ) : (
              <>
                {!initLoading ? (
                  <>
                    <div className={styles.payInfoTitle}>到手价格</div>
                    <div className={styles.priceWrapper}>
                      <div className={classNames(styles.price)}>
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
                            <div className={styles.priceItem} key={index}>
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
                    {hasLogin ? (
                      <>
                        <div className={styles.payChannelWrapper}>
                          <Radio.Group
                            value={payChannel}
                            onChange={onPayChannelChange}
                          >
                            {inWechat() && (
                              <div
                                className={classNames(
                                  styles.payChannelRow,
                                  payChannel === PAY_CHANNEL_WECHAT_JSAPI &&
                                    styles.selected,
                                )}
                                onClick={onPayChannelWechatClick}
                              >
                                <div className={styles.payChannelBasic}>
                                  <img
                                    src={weixinIcon}
                                    alt="微信支付"
                                    className={styles.payChannelIcon}
                                  />
                                  <span className={styles.payChannelTitle}>
                                    微信支付
                                  </span>
                                </div>
                                <RadioM
                                  className={styles.payChannelRadio}
                                  value={PAY_CHANNEL_WECHAT_JSAPI}
                                />
                              </div>
                            )}
                            {!inWechat() && (
                              <div
                                className={classNames(
                                  styles.payChannelRow,
                                  payChannel === PAY_CHANNEL_ZHIFUBAO &&
                                    styles.selected,
                                )}
                                onClick={onPayChannelZhifubaoClick}
                              >
                                <div className={styles.payChannelBasic}>
                                  <img
                                    src={zhifuboIcon}
                                    alt="支付宝支付"
                                    className={styles.payChannelIcon}
                                  />
                                  <span className={styles.payChannelTitle}>
                                    支付宝支付
                                  </span>
                                </div>
                                <RadioM
                                  className={styles.payChannelRadio}
                                  value={PAY_CHANNEL_ZHIFUBAO}
                                />
                              </div>
                            )}
                          </Radio.Group>
                        </div>
                        <div className={styles.buttonWrapper}>
                          <MainButtonM
                            className={styles.payButton}
                            onClick={handlePay}
                          >
                            支付
                          </MainButtonM>
                        </div>
                        <div className={styles.couponCodeWrapper}>
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
                      </>
                    ) : (
                      <div className={styles.loginButtonWrapper}>
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
              <img className={styles.payInfo} src={payInfoBg} alt="产品说明" />
            </div>
          </div>
        }
      />
      {couponCodeModalOpen && (
        <ModalM
          visible={couponCodeModalOpen}
          title="兑换码"
          onClose={onCouponCodeModalClose}
          style={{ width: '80%' }}
          className={styles.couponCodeModal}
          content={
            <>
              <div className={styles.couponCodeInputWrapper}>
                <SettingInputM
                  title="兑换码"
                  onChange={(e) => setCouponCode(e)}
                />
              </div>
              <div class={styles.buttonWrapper}>
                <MainButtonM
                  onClick={onCouponCodeOkClick}
                  className={styles.okButton}
                >
                  确定
                </MainButtonM>
              </div>
            </>
          }
        />
      )}
      {contextHolder}
    </>
  );
};

export default memo(PayModalM);
