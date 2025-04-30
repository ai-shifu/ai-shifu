import { Button, Modal, QRCode, message } from 'antd';
import { useShallow } from 'zustand/react/shallow';
import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './PayModal.module.scss';
import { useDisclosture } from 'common/hooks/useDisclosture';
import CouponCodeModal from './CouponCodeModal';
import { ORDER_STATUS, PAY_CHANNEL_WECHAT } from './constans';
import {
  getPayUrl,
  initOrder,
  initActiveOrder,
  queryOrder,
  applyDiscountCode,
} from 'Api/order';
import classNames from 'classnames';
import { useInterval } from 'react-use';
import paySucessBg from 'Assets/newchat/pay-success@2x.png';
import payInfoBg from 'Assets/newchat/pay-info-bg.png';
import PayModalFooter from './PayModalFooter';
import PayChannelSwitch from './PayChannelSwitch';
import { getStringEnv } from 'Utils/envUtils';
import MainButton from 'Components/MainButton';
import { useUserStore } from 'stores/useUserStore';
import { shifu } from 'Service/Shifu';
import { getCourseInfo } from 'Api/course';

const DEFAULT_QRCODE = 'DEFAULT_QRCODE';
const MAX_TIMEOUT = 1000 * 60 * 3;
const COUNTDOWN_INTERVAL = 1000;
const CompletedSection = memo(() => {
  const { t } = useTranslation();
  return (
    <div className={styles.completedSection}>
      <div className={styles.title}>{t('pay.paySuccess')}</div>
      <div className={styles.completeWrapper}>
        <img className={styles.paySuccessBg} src={paySucessBg} alt="" />
      </div>
      <PayModalFooter />
    </div>
  );
});

export const PayModal = ({
  open = false,
  onCancel,
  onOk,
  type = '',
  payload = {},
}) => {
  const { t } = useTranslation();
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
  const [messageApi, contextHolder] = message.useMessage();
  const [couponCode, setCouponCode] = useState('');
  const [originalPrice, setOriginalPrice] = useState('');
  const [priceItems, setPriceItems] = useState([]);

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
    hasLogin ? interval : null,
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
          setInterval(COUNTDOWN_INTERVAL);
        }
      }
    },
    [payChannel],
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

    const resp = await getCourseInfo(courseId);
    setPrice(resp.data.course_price);

    setIsLoading(false);
  }, [courseId]);

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

  const onLoginButtonClick = useCallback(() => {
    onCancel?.();
    shifu.loginTools.openLogin();
  }, [onCancel]);

  const {
    open: couponCodeModalOpen,
    onOpen: onCouponCodeModalOpen,
    onClose: onCouponCodeModalClose,
  } = useDisclosture();

  const _onCancel = useCallback(
    (e) => {
      onCancel?.(e);
    },
    [onCancel],
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
      refreshOrderQrcode();
      onCouponCodeModalClose();
    },
    [messageApi, onCouponCodeModalClose, orderId, refreshOrderQrcode],
  );

  const onPayChannelSelectChange = useCallback((e) => {
    setPayChannel(e.channel);
  }, []);

  useEffect(() => {
    if (!open || !hasLogin) {
      return;
    }
    loadPayInfo();
    setInitLoading(false);
  }, [hasLogin, loadPayInfo, open]);

  useEffect(() => {
    if (!hasLogin) {
      loadCourseInfo();
      setInitLoading(false);
    }
  }, [hasLogin, loadCourseInfo]);

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
        {!initLoading && (
          <div className={styles.payModalContent}>
            <div
              className={styles.introSection}
              style={{ backgroundImage: `url(${payInfoBg})` }}
            ></div>
            {isCompleted ? (
              <CompletedSection />
            ) : (
              <div className={styles.paySection}>
                <div className={styles.payInfoTitle}>到手价格</div>
                <div className={styles.priceWrapper}>
                  <div
                    className={classNames(
                      styles.price,
                      (isLoading || isTimeout) && styles.disabled,
                    )}
                  >
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
                    <div className={styles.originalPrice}>{originalPrice}</div>
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
                    <div className={styles.qrcodeWrapper}>
                      <QRCode
                        size={175}
                        value={qrUrl}
                        status={getQrcodeStatus()}
                        onRefresh={onQrcodeRefresh}
                        bordered={false}
                      />
                    </div>
                    <div className={styles.channelSwitchWrapper}>
                      <PayChannelSwitch
                        channel={payChannel}
                        onChange={onPayChannelSelectChange}
                      />
                    </div>
                    <div className={styles.couponCodeWrapper}>
                      <Button
                        type="link"
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
                    <MainButton onClick={onLoginButtonClick}>登录</MainButton>
                  </div>
                )}
                <PayModalFooter />
              </div>
            )}
          </div>
        )}
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
