import { useCallback, useEffect, useRef, useState } from 'react';
import { useInterval } from 'react-use';
import {
  applyDiscountCode,
  getPayUrl,
  initActiveOrder,
  initOrder,
  queryOrder,
  syncPaymentOrder,
  type PayUrlRequest,
  type PaymentChannel,
} from '@/c-api/order';
import type { LearnerPaymentAttemptContext } from '@/lib/paymentAnalytics';
import { ORDER_STATUS } from '../constans';

interface PriceItem {
  price_name: string;
  price: string;
  is_discount?: boolean;
}

const MAX_TIMEOUT = 1000 * 60 * 3;
const COUNTDOWN_INTERVAL = 1000;
const NATIVE_SYNC_INTERVAL = 1000 * 5;
const DIRECT_NATIVE_PAYMENT_CHANNELS = new Set<PaymentChannel>([
  'alipay',
  'wechatpay',
]);

function shouldSyncNativePaymentChannel(
  paymentChannel?: PaymentChannel,
): paymentChannel is 'alipay' | 'wechatpay' {
  return Boolean(
    paymentChannel && DIRECT_NATIVE_PAYMENT_CHANNELS.has(paymentChannel),
  );
}

export interface PaymentInfoState {
  channel: string;
  qrUrl: string;
  status?: number;
  paymentChannel?: PaymentChannel;
  paymentPayload?: Record<string, any>;
}

export interface PaymentPaidContext {
  confirmedAttempt: LearnerPaymentAttemptContext;
}

interface UsePaymentFlowOptions {
  type?: string;
  payload?: Record<string, any>;
  courseId: string;
  isLoggedIn: boolean;
  onOrderPaid?: (context?: PaymentPaidContext) => void;
  onPollingTimeout?: () => void;
}

interface OrderSnapshot {
  order_id: string;
  price: string;
  value_to_pay: string;
  price_item?: PriceItem[];
  status: number;
}

function isOrderPaid(snapshot?: OrderSnapshot | null): boolean {
  if (!snapshot) return false;
  const valueToPay =
    typeof snapshot.value_to_pay === 'string'
      ? snapshot.value_to_pay.trim()
      : '';
  const valueToPayNumber = Number(valueToPay);
  const isFreeOrder =
    valueToPay.length > 0 &&
    Number.isFinite(valueToPayNumber) &&
    valueToPayNumber <= 0;
  return snapshot.status === ORDER_STATUS.BUY_STATUS_SUCCESS || isFreeOrder;
}

export interface PaymentActionParams {
  channel: string;
  paymentChannel?: PaymentChannel;
  snapshot?: OrderSnapshot | null;
}

export interface PaymentCouponParams extends PaymentActionParams {
  code: string;
}

export interface PaymentSyncParams {
  paymentChannel?: PaymentChannel;
  confirmedAttempt?: LearnerPaymentAttemptContext;
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
  onPollingTimeout,
}: UsePaymentFlowOptions) => {
  const mountedRef = useRef(true);
  const nativeSyncLastAtRef = useRef(0);
  const pollingDeadlineAtRef = useRef(0);
  const pollingGenerationRef = useRef(0);
  const pollingInFlightGenerationRef = useRef<number | null>(null);
  const timeoutReportedGenerationRef = useRef<number | null>(null);
  const refreshGenerationRef = useRef(0);
  const completedRef = useRef(false);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const [orderId, setOrderIdState] = useState('');
  const orderIdRef = useRef('');
  const updateOrderId = useCallback((value: string) => {
    orderIdRef.current = value;
    setOrderIdState(value);
  }, []);

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

  const restartPollingWindow = useCallback(() => {
    pollingGenerationRef.current += 1;
    pollingInFlightGenerationRef.current = null;
    pollingDeadlineAtRef.current = Date.now() + MAX_TIMEOUT;
    setIsTimeout(false);
    setCountDownMs(MAX_TIMEOUT);
  }, []);

  useEffect(() => {
    if (!isLoggedIn) {
      setInitLoading(false);
    }
  }, [isLoggedIn]);

  const updateFromOrder = useCallback(
    (snapshot?: OrderSnapshot | null, paidContext?: PaymentPaidContext) => {
      if (!snapshot) return;
      setPrice(snapshot.value_to_pay);
      setOriginalPrice(snapshot.price);
      setPriceItems(
        snapshot.price_item?.filter(item => item?.is_discount) || [],
      );
      if (isOrderPaid(snapshot)) {
        const wasCompleted = completedRef.current;
        completedRef.current = true;
        setIsCompleted(true);
        setIsTimeout(false);
        setPollingActive(false);
        if (!wasCompleted) {
          if (paidContext) {
            onOrderPaid?.(paidContext);
          } else {
            onOrderPaid?.();
          }
        }
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
    refreshGenerationRef.current += 1;
    completedRef.current = false;
    setIsLoading(true);
    restartPollingWindow();
    setPaymentInfo(defaultPaymentInfo);
    nativeSyncLastAtRef.current = 0;
    try {
      const snapshot = await initOrderUniform();
      if (!mountedRef.current || !snapshot) {
        return snapshot;
      }
      updateOrderId(snapshot.order_id);
      setCouponCode('');
      setIsCompleted(false);
      updateFromOrder(snapshot);
      return snapshot;
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
        setInitLoading(false);
      }
    }
  }, [
    initOrderUniform,
    isLoggedIn,
    restartPollingWindow,
    updateFromOrder,
    updateOrderId,
  ]);

  const refreshPayment = useCallback(
    async ({ channel, paymentChannel, snapshot }: PaymentActionParams) => {
      const currentOrderId = orderIdRef.current;
      if (!currentOrderId || completedRef.current) return null;
      const refreshGeneration = ++refreshGenerationRef.current;
      setIsLoading(true);
      try {
        const current =
          snapshot ||
          ((await queryOrder({
            orderId: currentOrderId,
          })) as OrderSnapshot | null);
        if (!mountedRef.current || !current) {
          return null;
        }
        const currentSnapshot = current;
        if (
          refreshGeneration !== refreshGenerationRef.current ||
          completedRef.current
        ) {
          if (
            currentOrderId === orderIdRef.current &&
            isOrderPaid(currentSnapshot)
          ) {
            updateFromOrder(currentSnapshot);
          }
          return null;
        }
        updateFromOrder(current);
        if (isOrderPaid(currentSnapshot)) {
          return current;
        }
        const payload = await getPayUrl({
          channel,
          orderId: currentOrderId,
          paymentChannel,
        } as PayUrlRequest);
        if (
          !mountedRef.current ||
          refreshGeneration !== refreshGenerationRef.current ||
          !payload ||
          completedRef.current
        ) {
          return null;
        }
        setPaymentInfo({
          channel: payload.channel,
          qrUrl: typeof payload.qr_url === 'string' ? payload.qr_url : '',
          status: payload.status,
          paymentChannel: payload.payment_channel,
          paymentPayload: payload.payment_payload || {},
        });
        nativeSyncLastAtRef.current = 0;
        restartPollingWindow();
        if (payload.status === ORDER_STATUS.BUY_STATUS_SUCCESS) {
          const wasCompleted = completedRef.current;
          completedRef.current = true;
          setIsCompleted(true);
          setPollingActive(false);
          if (!wasCompleted) {
            onOrderPaid?.();
          }
        } else {
          setPollingActive(true);
        }
        return payload;
      } finally {
        if (
          mountedRef.current &&
          refreshGeneration === refreshGenerationRef.current
        ) {
          setIsLoading(false);
        }
      }
    },
    [onOrderPaid, restartPollingWindow, updateFromOrder],
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
        await refreshPayment({
          channel,
          paymentChannel,
          snapshot: resp as OrderSnapshot,
        });
      }
      return resp;
    },
    [refreshPayment, updateFromOrder],
  );

  useInterval(
    async () => {
      const generation = pollingGenerationRef.current;
      if (timeoutReportedGenerationRef.current === generation) {
        return;
      }
      const remainingMs = Math.max(
        pollingDeadlineAtRef.current - Date.now(),
        0,
      );
      setCountDownMs(remainingMs);
      if (remainingMs === 0) {
        setPollingActive(false);
        if (!completedRef.current) {
          setIsTimeout(true);
        }
      }
      if (pollingInFlightGenerationRef.current === generation) {
        return;
      }
      pollingInFlightGenerationRef.current = generation;
      let finalSnapshot: OrderSnapshot | null = null;

      try {
        if (!orderIdRef.current) {
          return;
        }
        const currentOrderId = orderIdRef.current;
        const nativePaymentChannel = paymentInfo.paymentChannel;
        if (shouldSyncNativePaymentChannel(nativePaymentChannel)) {
          const now = Date.now();
          if (now - nativeSyncLastAtRef.current >= NATIVE_SYNC_INTERVAL) {
            nativeSyncLastAtRef.current = now;
            try {
              await syncPaymentOrder({
                orderId: currentOrderId,
                paymentChannel: nativePaymentChannel,
              });
            } catch {
              // The regular order query below keeps polling while the provider sync is transiently unavailable.
            }
          }
        }

        const resp = await queryOrder({ orderId: currentOrderId });
        if (!mountedRef.current || !resp) {
          return;
        }
        const responseSnapshot = resp as OrderSnapshot;
        if (generation !== pollingGenerationRef.current) {
          if (
            currentOrderId === orderIdRef.current &&
            isOrderPaid(responseSnapshot)
          ) {
            updateFromOrder(responseSnapshot);
          }
          return;
        }
        finalSnapshot = responseSnapshot;
        updateFromOrder(finalSnapshot);
      } finally {
        if (pollingInFlightGenerationRef.current === generation) {
          pollingInFlightGenerationRef.current = null;
        }
        const timeoutReached = Date.now() >= pollingDeadlineAtRef.current;
        if (mountedRef.current && generation === pollingGenerationRef.current) {
          setCountDownMs(
            Math.max(pollingDeadlineAtRef.current - Date.now(), 0),
          );
          if (timeoutReached) {
            setPollingActive(false);
            if (!completedRef.current && !isOrderPaid(finalSnapshot)) {
              setIsTimeout(true);
            }
          }
        }
        const shouldFinalizeTimeout =
          timeoutReached &&
          mountedRef.current &&
          generation === pollingGenerationRef.current &&
          !completedRef.current &&
          timeoutReportedGenerationRef.current !== generation;
        if (shouldFinalizeTimeout) {
          timeoutReportedGenerationRef.current = generation;
          setPollingActive(false);
          if (!isOrderPaid(finalSnapshot)) {
            setIsTimeout(true);
            onPollingTimeout?.();
          }
        }
      }
    },
    isLoggedIn && pollingActive ? COUNTDOWN_INTERVAL : null,
  );

  const syncOrderStatus = useCallback(
    async (params: PaymentSyncParams = {}) => {
      if (!orderIdRef.current) {
        return null;
      }
      const syncPaymentChannel =
        params.paymentChannel ||
        (shouldSyncNativePaymentChannel(paymentInfo.paymentChannel)
          ? paymentInfo.paymentChannel
          : undefined);
      if (syncPaymentChannel) {
        await syncPaymentOrder({
          orderId: orderIdRef.current,
          paymentChannel: syncPaymentChannel,
        });
      }
      const resp = await queryOrder({ orderId: orderIdRef.current });
      if (!mountedRef.current || !resp) {
        return resp;
      }
      const paidContext = params.confirmedAttempt
        ? { confirmedAttempt: params.confirmedAttempt }
        : undefined;
      updateFromOrder(resp as OrderSnapshot, paidContext);
      return resp;
    },
    [paymentInfo.paymentChannel, updateFromOrder],
  );

  const resetState = useCallback(() => {
    refreshGenerationRef.current += 1;
    completedRef.current = false;
    updateOrderId('');
    setPrice('0');
    setOriginalPrice('');
    setPriceItems([]);
    setCouponCode('');
    setPaymentInfo(defaultPaymentInfo);
    nativeSyncLastAtRef.current = 0;
    restartPollingWindow();
    setIsLoading(false);
    setIsCompleted(false);
    setPollingActive(false);
  }, [restartPollingWindow, updateOrderId]);

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
