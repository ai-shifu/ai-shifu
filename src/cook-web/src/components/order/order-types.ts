export type OrderSummary = {
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
  coupon_codes: string[];
  created_at: string;
  updated_at: string;
};

export type OrderActivity = {
  active_id: string;
  active_name: string;
  price: string;
  status: number;
  status_key: string;
  created_at: string;
  updated_at: string;
};

export type OrderCoupon = {
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

export type OrderPayment = {
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

export type OrderDetail = {
  order: OrderSummary;
  activities: OrderActivity[];
  coupons: OrderCoupon[];
  payment: OrderPayment;
};
