import { Button, Modal, Select } from 'antd';
import { useCallback } from 'react';
import { memo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './PayModal.module.scss';
import { useDisclosture } from 'common/hooks/useDisclosture.js';
import CouponCodeModal from './CouponCodeModal.jsx';
import { QRCode } from 'antd';
import {
  ORDER_STATUS,
  PAY_CHANNEL_WECHAT,
  getPayChannelOptions,
} from './constans.js';
import {
  getPayUrl,
  initOrder,
  queryOrder,
  applyDiscountCode,
} from 'Api/order.js';
import { useEffect } from 'react';
import classNames from 'classnames';
import { useInterval } from 'react-use';
import { message } from 'antd';

import payInfoBg from 'Assets/newchat/pay-info-bg.png';
import PayLeft from './PayLeft.jsx';

const DEFAULT_QRCODE = 'DEFAULT_QRCODE';
const MAX_TIMEOUT = 1000 * 60 * 3;
const COUNTDOWN_INTERVAL = 1000;

export const PayModal = ({ open = false, onCancel, onOk }) => {
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [isTimeout, setIsTimeout] = useState(false);

  const [price, setPrice] = useState('');
  const [qrUrl, setQrUrl] = useState(DEFAULT_QRCODE);
  const [payChannel, setPayChannel] = useState(PAY_CHANNEL_WECHAT);
  const [interval, setInterval] = useState(null);
  const [orderId, setOrderId] = useState('');
  const [countDwon, setCountDown] = useState(MAX_TIMEOUT);
  const [messageApi, contextHolder] = message.useMessage();
  const [couponCode, setCouponCode] = useState('');
  const [discount, setDiscount] = useState('');

  useInterval(async () => {
    if (countDwon <= 0) {
      setIsTimeout(true);
      setInterval(null);
    }
    setCountDown(countDwon - COUNTDOWN_INTERVAL);

    const { data: resp } = await queryOrder({ orderId });

    if (resp.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
      setInterval(null);
      onOk?.();
      return;
    }

    setDiscount(resp.discount);
    setPrice(resp.value_to_pay);
  }, interval);

  const refreshOrderQrcode = useCallback(
    async (orderId) => {
      const { data: qrcodeResp } = await getPayUrl({
        channel: payChannel,
        orderId,
      });

      setQrUrl(qrcodeResp.qr_url);
      setCountDown(MAX_TIMEOUT);
      setInterval(COUNTDOWN_INTERVAL);
    },
    [payChannel]
  );

  const loadPayInfo = useCallback(async () => {
    setIsLoading(true);
    setIsTimeout(false);
    setQrUrl(DEFAULT_QRCODE);
    setPrice('0');
    setOrderId('');
    setInterval(null);
    setCouponCode('');
    setDiscount('');

    const { data: resp } = await initOrder();
    if (resp.status !== ORDER_STATUS.BUY_STATUS_INIT && resp.status !== ORDER_STATUS.BUY_STATUS_TO_BE_PAID) {
      return;
    }

    setPrice(resp.value_to_pay);
    const orderId = resp.order_id;
    setOrderId(orderId);
    await refreshOrderQrcode(orderId);
    setIsLoading(false);
  }, [refreshOrderQrcode]);

  const onQrcodeRefresh = useCallback(() => {
    loadPayInfo();
  }, [loadPayInfo]);

  const getQrcodeStatus = useCallback(() => {
    if (isLoading) {
      return 'loading';
    }

    if (isTimeout) {
      return 'expired';
    }

    return 'active';
  }, [isLoading, isTimeout]);

  useEffect(() => {
    if (!open) {
      return;
    }
    loadPayInfo();
  }, [loadPayInfo, open]);

  const {
    open: couponCodeModalOpen,
    onOpen: onCouponCodeModalOpen,
    onClose: onCouponCodeModalClose,
  } = useDisclosture();

  const _onCancel = useCallback(
    (e) => {
      onCancel?.(e);
    },
    [onCancel]
  );

  const onCouponCodeClick = useCallback(() => {
    onCouponCodeModalOpen();
  }, [onCouponCodeModalOpen]);

  const onCouponCodeOk = useCallback(
    async (values) => {
      const { couponCode } = values;
      setCouponCode(couponCode);
      const resp = await applyDiscountCode({ orderId, code: couponCode });
      if (resp.code !== 0) {
        messageApi.error(resp.message);
        return;
      }

      onCouponCodeModalClose();
      refreshOrderQrcode();
    },
    [messageApi, onCouponCodeModalClose, orderId, refreshOrderQrcode]
  );

  const onPayChannelSelectChange = useCallback((e) => {
    setPayChannel(e);
  }, []);

  return (
    <>
      <Modal
        title={null}
        open={open}
        footer={null}
        onCancel={_onCancel}
        className={styles.payModal}
        width="700px"
        height="588px"
        maskClosable={false}
      >
        <div className={styles.payModalContent}>
          <div
            className={styles.introSection}
            style={{ backgroundImage: `url(${payInfoBg})` }}
          >
            <PayLeft />
          </div>
          <div className={styles.paySection}>
            <div className={styles.payInfoTitle}>首发特惠</div>
            <div className={styles.priceWrapper}>
              <div
                className={classNames(
                  styles.price,
                  (isLoading || isTimeout) && styles.disabled
                )}
              >
                <span className={styles.priceSign}>￥</span>
                <span className={styles.priceNumber}>{price}</span>
              </div>
            </div>
            <div className={styles.discountTipWrapper}>
              <div className={styles.discountTip}>已节省： {discount || '0.00'}</div>
            </div>
            <div className={styles.payChannelWrapper}>
              <span>支付方式：</span>
              <Select
                className={styles.payChannelSelect}
                options={getPayChannelOptions()}
                value={payChannel}
                style={{ width: '120px' }}
                onChange={onPayChannelSelectChange}
              />
            </div>
            <div className={styles.qrcodeWrapper}>
              <QRCode
                size={183}
                value={qrUrl}
                status={getQrcodeStatus()}
                onRefresh={onQrcodeRefresh}
                bordered={false}
              />
            </div>
            <div className={styles.couponCodeWrapper}>
              <Button
                type="link"
                onClick={onCouponCodeClick}
                className={styles.couponCodeButton}
              >
                {!couponCode ? '使用优惠券' : '修改优惠券'}
              </Button>
            </div>
          </div>
        </div>
      </Modal>
      {couponCodeModalOpen && (
        <CouponCodeModal
          open={couponCodeModalOpen}
          onCancel={onCouponCodeModalClose}
          onOk={onCouponCodeOk}
        />
      )}
      {contextHolder}
    </>
  );
};

export default memo(PayModal);
