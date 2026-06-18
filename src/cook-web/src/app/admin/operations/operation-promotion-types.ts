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
  ops_states?: string[];
  enabled?: boolean;
  computed_status: string;
  computed_status_key: string;
  created_user_bid?: string;
  created_user_name?: string;
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
  enabled?: boolean;
  created_user_bid?: string;
  created_user_name?: string;
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

export type AdminBillingCampaignProductOption = {
  product_bid: string;
  product_code: string;
  product_type: 'plan' | 'topup';
  display_name: string;
  description: string;
  currency: string;
  price_amount: number;
  credit_amount: number;
  billing_interval: string;
  billing_interval_count: number;
  campaign_discount_type?: 'fixed' | 'percent' | null;
  campaign_discount_amount: number;
  campaign_discount_percent: number;
  campaign_price_amount: number;
  campaign_bonus_credit_amount: number;
};

export type AdminBillingCampaignProductOptions = {
  plans: AdminBillingCampaignProductOption[];
  topups: AdminBillingCampaignProductOption[];
};

export type AdminBillingCampaignItem = {
  campaign_bid: string;
  name: string;
  note: string;
  benefit_type: 'discount' | 'bonus';
  discount_type?: 'fixed' | 'percent' | null;
  discount_amount: number;
  discount_percent: number;
  bonus_credit_amount: number;
  product_count: number;
  product_types: string[];
  product_names: string[];
  has_custom_product_rules: boolean;
  computed_status: 'active' | 'upcoming' | 'ended' | 'inactive';
  hit_order_count: number;
  start_at: string;
  end_at: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminBillingCampaignDetail = {
  campaign: AdminBillingCampaignItem;
  products: AdminBillingCampaignProductOption[];
  created_user_bid: string;
  updated_user_bid: string;
};

export type AdminReferralCampaignStatus =
  | 'active'
  | 'not_started'
  | 'ended'
  | 'inactive';

export type AdminReferralCampaignItem = {
  campaign_bid: string;
  campaign_code: string;
  campaign_name: string;
  campaign_status: number;
  computed_status: AdminReferralCampaignStatus;
  enabled: boolean;
  feature_flag_key: string;
  starts_at: string;
  ends_at: string;
  invite_route_template: string;
  inviter_eligibility: Record<string, unknown>;
  invitee_eligibility: Record<string, unknown>;
  invitee_benefit_policy: string;
  rules_copy_i18n_key: string;
  reward_rule_bid: string;
  rule_code: string;
  rule_status: number;
  reward_product_code: string;
  reward_cycle_count: number;
  reward_credit_amount: string | null;
  reward_credit_validity_days: number;
  reward_cap_scope: 'none' | 'per_inviter' | 'per_campaign' | string;
  reward_cap_count: number | null;
  reward_timing_policy: string;
  priority: number;
  relation_count: number;
  reward_count: number;
  created_at: string;
  updated_at: string;
};

export type AdminReferralCampaignDetail = {
  campaign: AdminReferralCampaignItem;
};
