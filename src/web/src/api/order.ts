import request from '@/lib/request';

export type PaymentChannel = 'pingxx' | 'stripe' | 'alipay' | 'wechatpay';

export interface StripePaymentPayload {
  mode?: 'payment_intent' | 'checkout_session';
  client_secret?: string;
  checkout_session_url?: string;
  checkout_session_id?: string;
  payment_intent_id?: string;
  latest_charge_id?: string;
}

export interface NativePaymentPayload {
  mode?: 'jsapi';
  prepay_id?: string;
  jsapi_params?: Record<string, string>;
  credential?: Record<string, unknown>;
  qr_url?: string | Record<string, string>;
}

export interface PayUrlResponse {
  order_id: string;
  user_id: string;
  price: string;
  channel: string;
  qr_url: string | Record<string, string>;
  payment_channel?: PaymentChannel;
  payment_payload?:
    | StripePaymentPayload
    | NativePaymentPayload
    | Record<string, any>;
  status?: number;
}

export type PayUrlRequest = {
  channel: string;
  orderId: string;
  paymentChannel?: PaymentChannel;
};

export interface PaymentDetailResponse {
  payment_channel: PaymentChannel;
  order_bid: string;
  course_id: string;
  status: number;
}

// Create order
export const initOrder = (course_id: string) => {
  return request.post('/api/order/init-order', { course_id });
};

// Retrieve payment URL
export const getPayUrl = ({
  channel,
  orderId,
  paymentChannel,
}: PayUrlRequest): Promise<PayUrlResponse> => {
  return request.post('/api/order/reqiure-to-pay', {
    channel,
    order_id: orderId,
    payment_channel: paymentChannel,
  }) as Promise<PayUrlResponse>;
};

// Query order status
export const queryOrder = ({ orderId }) => {
  return request.post('/api/order/query-order', { order_id: orderId });
};

// Apply discount code
export const applyDiscountCode = ({ orderId, code }) => {
  return request.post('/api/order/apply-discount', {
    discount_code: code,
    order_id: orderId,
  });
};

export const getPaymentDetail = ({
  orderId,
}: {
  orderId: string;
}): Promise<PaymentDetailResponse> => {
  return request.post('/api/order/payment-detail', {
    order_id: orderId,
  }) as Promise<PaymentDetailResponse>;
};

// generate active order
export const initActiveOrder = ({ recordId, action, courseId }) => {
  return request.post('/api/click2cash/generate-active-order', {
    course_id: courseId,
    action,
    record_id: recordId,
  });
};

export const syncStripeCheckout = ({
  orderId,
  sessionId,
}: {
  orderId: string;
  sessionId?: string;
}): Promise<PaymentDetailResponse> => {
  return request.post('/api/order/stripe/sync', {
    order_id: orderId,
    session_id: sessionId,
  }) as Promise<PaymentDetailResponse>;
};

export const syncPaymentOrder = ({
  orderId,
  paymentChannel,
}: {
  orderId: string;
  paymentChannel?: PaymentChannel;
}): Promise<PaymentDetailResponse> => {
  return request.post('/api/order/payment/sync', {
    order_id: orderId,
    payment_channel: paymentChannel,
  }) as Promise<PaymentDetailResponse>;
};
