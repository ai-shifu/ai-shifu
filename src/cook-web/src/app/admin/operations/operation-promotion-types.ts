export type AdminPromotionSummary = {
  total: number;
  active: number;
  usage_count: number;
  latest_usage_at: string;
  covered_courses: number;
  discount_amount: string;
};

export type AdminPromotionListResponse<T> = {
  summary: AdminPromotionSummary;
  items: T[];
  page: number;
  page_size: number;
  total: number;
  page_count: number;
};

export type AdminPromotionCouponItem = {
  coupon_bid: string;
  name: string;
  code: string;
  usage_type: number;
  usage_type_key: string;
  discount_type: number;
  discount_type_key: string;
  value: string;
  scope_type: string;
  shifu_bid: string;
  course_name: string;
  start_at: string;
  end_at: string;
  total_count: number;
  used_count: number;
  computed_status: string;
  computed_status_key: string;
  created_at: string;
  updated_at: string;
};

export type AdminPromotionCouponDetail = {
  coupon: AdminPromotionCouponItem;
  created_user_bid: string;
  created_user_name: string;
  updated_user_bid: string;
  updated_user_name: string;
  remaining_count: number;
  latest_used_at: string;
};

export type AdminPromotionCouponUsageItem = {
  coupon_usage_bid: string;
  code: string;
  status: number;
  status_key: string;
  user_bid: string;
  user_mobile: string;
  user_email: string;
  user_nickname: string;
  shifu_bid: string;
  course_name: string;
  order_bid: string;
  order_status: number;
  order_status_key: string;
  payable_price: string;
  discount_amount: string;
  paid_price: string;
  used_at: string;
  updated_at: string;
};

export type AdminPromotionCouponCodeItem = {
  coupon_usage_bid: string;
  code: string;
  status: number;
  status_key: string;
  user_bid: string;
  user_mobile: string;
  user_email: string;
  user_nickname: string;
  order_bid: string;
  used_at: string;
  updated_at: string;
};

export type AdminPromotionCampaignItem = {
  promo_bid: string;
  name: string;
  shifu_bid: string;
  course_name: string;
  apply_type: number;
  discount_type: number;
  discount_type_key: string;
  value: string;
  channel: string;
  start_at: string;
  end_at: string;
  computed_status: string;
  computed_status_key: string;
  applied_order_count: number;
  has_redemptions: boolean;
  total_discount_amount: string;
  created_at: string;
  updated_at: string;
};

export type AdminPromotionCampaignDetail = {
  campaign: AdminPromotionCampaignItem;
  description: string;
  created_user_bid: string;
  created_user_name: string;
  updated_user_bid: string;
  updated_user_name: string;
  latest_applied_at: string;
};

export type AdminPromotionCampaignRedemptionItem = {
  redemption_bid: string;
  user_bid: string;
  user_mobile: string;
  user_email: string;
  user_nickname: string;
  order_bid: string;
  order_status: number;
  order_status_key: string;
  payable_price: string;
  discount_amount: string;
  paid_price: string;
  status: number;
  status_key: string;
  applied_at: string;
  updated_at: string;
};
