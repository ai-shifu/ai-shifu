import { useCallback, useEffect, useRef, useState } from 'react';
import { useInterval } from 'react-use';
import {
  applyDiscountCode,
  getPayUrl,
  initActiveOrder,
  initOrder,
  queryOrder,
  type PayUrlRequest,
  type PayUrlResponse,
  type PaymentChannel,
} from '@/c-api/order';
import { ORDER_STATUS } from '../constans';

interface PriceItem {
  price_name: string;
  price: string;
  is_discount?: boolean;
}

const MAX_TIMEOUT = 1000 * 60 * 3;
const COUNTDOWN_INTERVAL = 1000;

export interface PaymentInfoState {
  channel: string;
  qrUrl: string;
  status?: number;
  paymentChannel?: PaymentChannel;
  paymentPayload?: Record<string, any>;
}

interface UsePaymentFlowOptions {
  type?: string;
  payload?: Record<string, any>;
  courseId: string;
  isLoggedIn: boolean;
  onOrderPaid?: () => void;
}

interface OrderSnapshot {
  order_id: string;
  price: string;
  value_to_pay: string;
  price_item?: PriceItem[];
  status: number;
}

export interface PaymentActionParams {
  channel: string;
  paymentChannel?: PaymentChannel;
}

export interface PaymentCouponParams extends PaymentActionParams {
  code: string;
}

const defaultPaymentInfo: PaymentInfoState = {
  channel: '',
  qrUrl: '',
  status: undefined,
  paymentChannel: undefined,
  paymentPayload: {},
};

export const usePaymentFlow = ({
  type,
  payload,
  courseId,
  isLoggedIn,
  onOrderPaid,
}: UsePaymentFlowOptions) => {
  const mountedRef = useRef(true);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const [orderId, setOrderId] = useState('');
  const orderIdRef = useRef('');
  useEffect(() => {
    orderIdRef.current = orderId;
  }, [orderId]);

  const [price, setPrice] = useState('0');
  const [originalPrice, setOriginalPrice] = useState('');
  const [priceItems, setPriceItems] = useState<PriceItem[]>([]);
  const [couponCode, setCouponCode] = useState('');
  const [paymentInfo, setPaymentInfo] =
    useState<PaymentInfoState>(defaultPaymentInfo);
  const [isLoading, setIsLoading] = useState(false);
  const [initLoading, setInitLoading] = useState(true);
  const [isTimeout, setIsTimeout] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [countDownMs, setCountDownMs] = useState(MAX_TIMEOUT);
  const [pollingActive, setPollingActive] = useState(false);

  useEffect(() => {
    if (!isLoggedIn) {
      setInitLoading(false);
    }
  }, [isLoggedIn]);

  const updateFromOrder = useCallback(
    (snapshot?: OrderSnapshot | null) => {
      if (!snapshot) return;
      setPrice(snapshot.value_to_pay);
      setOriginalPrice(snapshot.price);
      setPriceItems(
        snapshot.price_item?.filter(item => item?.is_discount) || [],
      );
      if (snapshot.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
        setIsCompleted(true);
        setPollingActive(false);
        onOrderPaid?.();
      }
    },
    [onOrderPaid],
  );

  const initOrderUniform = useCallback(async () => {
    if (type === 'active') {
      const { recordId = '', action = '' } = (payload || {}) as {
        recordId?: string;
        action?: string;
      };
      return initActiveOrder({
        courseId,
        recordId,
        action,
      });
    }
    return initOrder(courseId);
  }, [courseId, payload, type]);

  const initializeOrder = useCallback(async () => {
    if (!isLoggedIn) {
      return null;
    }
    setIsLoading(true);
    setIsTimeout(false);
    setCountDownMs(MAX_TIMEOUT);
    setPaymentInfo(defaultPaymentInfo);
    try {
      const snapshot = await initOrderUniform();
      if (!mountedRef.current || !snapshot) {
        return snapshot;
      }
      setOrderId(snapshot.order_id);
      setCouponCode('');
      setIsCompleted(
        snapshot.status === ORDER_STATUS.BUY_STATUS_SUCCESS ? true : false,
      );
      updateFromOrder(snapshot);
      return snapshot;
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
        setInitLoading(false);
      }
    }
  }, [initOrderUniform, isLoggedIn, updateFromOrder]);

  const refreshPayment = useCallback(
    async ({ channel, paymentChannel }: PaymentActionParams) => {
      if (!orderIdRef.current) return null;
      setIsLoading(true);
      try {
        const payload = await getPayUrl({
          channel,
          orderId: orderIdRef.current,
          paymentChannel,
        } as PayUrlRequest);
        if (!mountedRef.current || !payload) {
          return payload;
        }
        setPaymentInfo({
          channel: payload.channel,
          qrUrl: payload.qr_url,
          status: payload.status,
          paymentChannel: payload.payment_channel,
          paymentPayload: payload.payment_payload || {},
        });
        setIsTimeout(false);
        setCountDownMs(MAX_TIMEOUT);
        if (payload.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
          setIsCompleted(true);
          setPollingActive(false);
          onOrderPaid?.();
        } else {
          setPollingActive(true);
        }
        return payload;
      } finally {
        if (mountedRef.current) {
          setIsLoading(false);
        }
      }
    },
    [onOrderPaid],
  );

  const applyCoupon = useCallback(
    async ({ code, channel, paymentChannel }: PaymentCouponParams) => {
      if (!orderIdRef.current) return null;
      const resp = await applyDiscountCode({
        orderId: orderIdRef.current,
        code,
      });
      if (!mountedRef.current || !resp) {
        return resp;
      }
      setCouponCode(code);
      updateFromOrder(resp as OrderSnapshot);
      if (
        resp.status === ORDER_STATUS.BUY_STATUS_INIT ||
        resp.status === ORDER_STATUS.BUY_STATUS_TO_BE_PAID
      ) {
        await refreshPayment({ channel, paymentChannel });
      }
      return resp;
    },
    [refreshPayment, updateFromOrder],
  );

  useInterval(
    async () => {
      setCountDownMs(prev => {
        if (prev <= COUNTDOWN_INTERVAL) {
          setIsTimeout(true);
          setPollingActive(false);
          return 0;
        }
        return prev - COUNTDOWN_INTERVAL;
      });

      if (!orderIdRef.current) {
        return;
      }
      const resp = await queryOrder({ orderId: orderIdRef.current });
      if (!mountedRef.current || !resp) {
        return;
      }
      updateFromOrder(resp as OrderSnapshot);
    },
    isLoggedIn && pollingActive ? COUNTDOWN_INTERVAL : null,
  );

  const syncOrderStatus = useCallback(async () => {
    if (!orderIdRef.current) {
      return null;
    }
    const resp = await queryOrder({ orderId: orderIdRef.current });
    if (!mountedRef.current || !resp) {
      return resp;
    }
    updateFromOrder(resp as OrderSnapshot);
    return resp;
  }, [updateFromOrder]);

  const resetState = useCallback(() => {
    setOrderId('');
    setPrice('0');
    setOriginalPrice('');
    setPriceItems([]);
    setCouponCode('');
    setPaymentInfo(defaultPaymentInfo);
    setIsTimeout(false);
    setIsCompleted(false);
    setCountDownMs(MAX_TIMEOUT);
    setPollingActive(false);
  }, []);

  return {
    orderId,
    price,
    originalPrice,
    priceItems,
    couponCode,
    setCouponCode,
    paymentInfo,
    isLoading,
    initLoading,
    isTimeout,
    isCompleted,
    countDownMs,
    initializeOrder,
    refreshPayment,
    applyCoupon,
    syncOrderStatus,
    resetState,
  };
};
