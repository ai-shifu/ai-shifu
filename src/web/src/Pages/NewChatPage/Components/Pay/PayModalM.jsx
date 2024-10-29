import { memo, useState } from 'react';
import ModalM from 'Components/m/ModalM.jsx';
import styles from './PayModalM.module.scss';
import classNames from 'classnames';
import PayTotalDiscount from './PayTotalDiscount.jsx';

import weixinIcon from 'Assets/newchat/weixin.png';
import zhifuboIcon from 'Assets/newchat/zhifubao.png';

import RadioM from 'Components/m/RadioM.jsx';
import { Radio } from 'antd-mobile';
import {
  PAY_CHANNEL_WECHAT_JSAPI,
  PAY_CHANNEL_ZHIFUBAO,
  ORDER_STATUS,
} from './constans.js';
import MainButtonM from 'Components/m/MainButtonM.jsx';
import payInfoBg from 'Assets/newchat/pay-info-bg-m.png';
import { useEffect } from 'react';

import { getPayUrl, initOrder, applyDiscountCode } from 'Api/order.js';
import { useWechat } from 'common/hooks/useWechat.js';
import { message } from 'antd';
import { inWechat } from 'constants/uiConstants.js';
import { useDisclosture } from 'common/hooks/useDisclosture.js';
import { useCallback } from 'react';
import { SettingInputM } from 'Components/m/SettingInputM.jsx';
import PayModalFooter from './PayModalFooter.jsx';
import contactBzWechatImg from 'Assets/newchat/contact-bz-wechat.png';
import { getStringEnv } from 'Utils/envUtils';
const CompletedSection = memo(() => {
  return (
    <div className={styles.completedSection}>
      <div className={styles.title}>添加真人助教</div>
      <div className={styles.completeWrapper}>
        <div className={styles.description}>
          <div>感谢你的信任！期待接下来的学习～</div>
          <div>
            请务必添加你的真人助教，学习课程时，遇到任何问题记得来找我！
          </div>
        </div>
        <div className={styles.qrcodeWrapper2}>
          <img
            className={styles.qrcode}
            src={contactBzWechatImg}
            alt="联系我"
          />
          <div>用微信扫码二维码</div>
        </div>
      </div>
    </div>
  );
});

export const PayModalM = ({ open = false, onCancel, onOk }) => {
  const [price, setPrice] = useState('0.00');
  const [totalDiscount, setTotalDiscount] = useState('');
  const [payChannel, setPayChannel] = useState(
    inWechat() ? PAY_CHANNEL_WECHAT_JSAPI : PAY_CHANNEL_ZHIFUBAO
  );
  const [isCompleted, setIsCompleted] = useState(false);
  const [orderId, setOrderId] = useState('');
  const [couponCode, setCouponCode] = useState('');
  const { payByJsApi } = useWechat();
  const [messageApi, contextHolder] = message.useMessage();
  const {
    open: couponCodeModalOpen,
    onClose: onCouponCodeModalClose,
    onOpen: onCouponCodeModalOpen,
  } = useDisclosture();
  const courseId = getStringEnv('courseId');
  useEffect(() => {
    (async () => {

      const { data: resp } = await initOrder(courseId);
      setPrice(resp.value_to_pay);
      const orderId = resp.order_id;
      setOrderId(orderId);
      setTotalDiscount(resp.discount);

      if (resp.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
        setIsCompleted(true);
      }
    })();
  }, []);

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
                <div className={styles.payInfoTitle}>首发特惠</div>
                <div className={styles.priceWrapper}>
                  <div
                    className={classNames(styles.price)}
                  >
                    <span className={styles.priceSign}>￥</span>
                    <span className={styles.priceNumber}>{price}</span>
                  </div>
                </div>
                <div className={styles.totalDiscountWrapper}>
                  <PayTotalDiscount discount={totalDiscount} />
                </div>
                <div className={styles.payChannelWrapper}>
                  <Radio.Group value={payChannel} onChange={onPayChannelChange}>
                    {inWechat() && (
                      <div
                        className={classNames(
                          styles.payChannelRow,
                          payChannel === PAY_CHANNEL_WECHAT_JSAPI &&
                            styles.selected
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
                          payChannel === PAY_CHANNEL_ZHIFUBAO && styles.selected
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
                  <MainButtonM className={styles.payButton} onClick={handlePay}>
                    支付
                  </MainButtonM>
                </div>
                <div className={styles.couponCodeWrapper}>
                  <MainButtonM
                    className={styles.couponCodeButton}
                    fill="none"
                    onClick={onCouponCodeButtonClick}
                  >
                    {'使用兑换码 >'}
                  </MainButtonM>
                </div>
              </>
            )}

            <PayModalFooter className={styles.protocal} />
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
