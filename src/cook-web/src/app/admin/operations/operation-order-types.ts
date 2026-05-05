type LooseString = string & {};

export type AdminOperationOrderSource =
  | 'user_purchase'
  | 'coupon_redeem'
  | 'import_activation'
  | 'open_api'
  | LooseString;

export type AdminOperationOrderItem = {
  order_bid: string;
  shifu_bid: string;
  shifu_name: string;
  user_bid: string;
  user_mobile: string;
  user_email: string;
  user_nickname: string;
  payable_price: string;
  paid_price: string;
  discount_amount: string;
  status: number;
  status_key: string;
  payment_channel: string;
  payment_channel_key: string;
  order_source: AdminOperationOrderSource;
  order_source_key: string;
  coupon_codes: string[];
  created_at: string;
  updated_at: string;
};

export type AdminOperationOrderListResponse = {
  items: AdminOperationOrderItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type AdminOperationOrderActivity = {
  active_id: string;
  active_name: string;
  price: string;
  status: number;
  status_key: string;
  created_at: string;
  updated_at: string;
};

export type AdminOperationOrderCoupon = {
  coupon_bid: string;
  code: string;
  name: string;
  discount_type: number;
  discount_type_key: string;
  value: string;
  status: number;
  status_key: string;
  created_at: string;
  updated_at: string;
};

export type AdminOperationOrderPayment = {
  payment_channel: string;
  payment_channel_key: string;
  status: number;
  status_key: string;
  amount: string;
  currency: string;
  payment_intent_id: string;
  checkout_session_id: string;
  latest_charge_id: string;
  receipt_url: string;
  payment_method: string;
  transaction_no: string;
  charge_id: string;
  channel: string;
  created_at: string;
  updated_at: string;
};

export type AdminOperationOrderDetailResponse = {
  order: AdminOperationOrderItem;
  activities: AdminOperationOrderActivity[];
  coupons: AdminOperationOrderCoupon[];
  payment: AdminOperationOrderPayment;
};
