export type BillingCenterTab =
  | 'plans'
  | 'ledger'
  | 'orders'
  | 'entitlements'
  | 'domains'
  | 'reports';

export type AdminBillingConsoleTab =
  | 'subscriptions'
  | 'orders'
  | 'exceptions'
  | 'entitlements'
  | 'domains'
  | 'reports';

export type BillingProvider = 'stripe' | 'pingxx' | 'manual';

export type BillingPingxxChannel = 'wx_pub_qr' | 'alipay_qr';

export type BillingCapabilityStatus =
  | 'active'
  | 'default_disabled'
  | 'internal_only';

export type BillingPaymentMode = 'subscription' | 'one_time';

export type BillingPlanInterval = 'day' | 'month' | 'year';

export type BillingOrderStatus =
  | 'init'
  | 'pending'
  | 'paid'
  | 'failed'
  | 'refunded'
  | 'canceled'
  | 'timeout';

export type BillingOrderType =
  | 'subscription_start'
  | 'subscription_upgrade'
  | 'subscription_renewal'
  | 'topup'
  | 'manual'
  | 'refund';

export type BillingSubscriptionStatus =
  | 'draft'
  | 'active'
  | 'past_due'
  | 'paused'
  | 'cancel_scheduled'
  | 'canceled'
  | 'expired';

export type BillingBucketCategory = 'subscription' | 'topup';

export type BillingBucketSourceType =
  | 'subscription'
  | 'topup'
  | 'gift'
  | 'refund'
  | 'manual'
  | 'usage';

export type BillingBucketStatus =
  | 'active'
  | 'exhausted'
  | 'expired'
  | 'canceled';

export type BillingDomainBindingStatus =
  | 'pending'
  | 'verified'
  | 'failed'
  | 'disabled';

export type BillingDomainVerificationMethod = 'dns_txt';

export type BillingDomainSslStatus = 'not_requested' | 'pending' | 'issued';

export type BillingPriorityClass = 'standard' | 'priority' | 'vip';

export type BillingAnalyticsTier = 'basic' | 'advanced' | 'enterprise';

export type BillingSupportTier = 'self_serve' | 'business_hours' | 'priority';

export type BillingLedgerEntryType =
  | 'grant'
  | 'consume'
  | 'refund'
  | 'expire'
  | 'adjustment'
  | 'hold'
  | 'release';

export type BillingMetricName =
  | 'llm_input_tokens'
  | 'llm_cache_tokens'
  | 'llm_output_tokens'
  | 'tts_request_count'
  | 'tts_output_chars'
  | 'tts_input_chars';

export type BillingRoundingMode = 'ceil' | 'floor' | 'round';

export type BillingUsageScene = 'debug' | 'preview' | 'production';

export type BillingRenewalEventType =
  | 'renewal'
  | 'retry'
  | 'cancel_effective'
  | 'downgrade_effective'
  | 'expire'
  | 'reconcile';

export type BillingRenewalEventStatus =
  | 'pending'
  | 'processing'
  | 'succeeded'
  | 'failed'
  | 'canceled';

export type BillingPagedResponse<TItem> = {
  items: TItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type BillingCapabilityEntryPoint = {
  kind: 'route' | 'task' | 'cli' | 'config';
  method?: string | null;
  path?: string | null;
  name?: string | null;
};

export type BillingCapability = {
  key: string;
  status: BillingCapabilityStatus;
  audience: string;
  user_visible: boolean;
  default_enabled: boolean;
  entry_points: BillingCapabilityEntryPoint[];
  notes: string[];
};

export type BillingRouteItem = {
  method: string;
  path: string;
};

export type BillingBootstrap = {
  service: string;
  status: string;
  path_prefix: string;
  creator_routes: BillingRouteItem[];
  admin_routes: BillingRouteItem[];
  capabilities: BillingCapability[];
  notes: string[];
};

export type BillingPlan = {
  product_bid: string;
  product_code: string;
  product_type: 'plan';
  display_name: string;
  description: string;
  billing_interval: BillingPlanInterval;
  billing_interval_count: number;
  currency: string;
  price_amount: number;
  credit_amount: number;
  auto_renew_enabled: boolean;
  highlights?: string[];
  status_badge_key?: string;
};

export type BillingTopupProduct = {
  product_bid: string;
  product_code: string;
  product_type: 'topup';
  display_name: string;
  description: string;
  currency: string;
  price_amount: number;
  credit_amount: number;
  highlights?: string[];
  status_badge_key?: string;
};

export type BillingSubscription = {
  subscription_bid: string;
  product_bid: string;
  product_code: string;
  status: BillingSubscriptionStatus;
  billing_provider: BillingProvider;
  current_period_start_at: string | null;
  current_period_end_at: string | null;
  grace_period_end_at: string | null;
  cancel_at_period_end: boolean;
  next_product_bid: string | null;
  last_renewed_at: string | null;
  last_failed_at: string | null;
};

export type BillingWalletBucket = {
  wallet_bucket_bid: string;
  category: BillingBucketCategory;
  source_type: BillingBucketSourceType;
  source_bid: string;
  available_credits: number;
  effective_from: string;
  effective_to: string | null;
  priority: number;
  status: BillingBucketStatus;
};

export type BillingWalletBucketList = {
  items: BillingWalletBucket[];
};

export type BillingMetricBreakdownItem = {
  billing_metric: BillingMetricName;
  billing_metric_code?: number;
  raw_amount: number;
  unit_size: number;
  rounded_units?: number;
  credits_per_unit: number;
  rounding_mode: BillingRoundingMode;
  consumed_credits: number;
};

export type BillingBucketMetricBreakdownItem = {
  billing_metric: BillingMetricName;
  billing_metric_code?: number;
  consumed_credits: number;
};

export type BillingBucketBreakdownItem = {
  wallet_bucket_bid: string;
  bucket_category: string;
  source_type: BillingBucketSourceType | string;
  source_bid: string;
  consumed_credits: number;
  effective_from?: string | null;
  effective_to?: string | null;
  metric_breakdown?: BillingBucketMetricBreakdownItem[];
};

export type BillingLedgerMetadata = {
  usage_bid?: string;
  usage_type?: BillingUsageType | number | null;
  usage_scene?: BillingUsageScene;
  course_name?: string;
  user_identify?: string;
  provider?: string;
  model?: string;
  metric_breakdown?: BillingMetricBreakdownItem[];
  bucket_breakdown?: BillingBucketBreakdownItem[];
};

export type BillingLedgerItem = {
  ledger_bid: string;
  wallet_bucket_bid: string;
  entry_type: BillingLedgerEntryType;
  source_type: BillingBucketSourceType;
  source_bid: string;
  idempotency_key: string;
  amount: number;
  balance_after: number;
  expires_at: string | null;
  consumable_from: string | null;
  metadata: BillingLedgerMetadata;
  created_at: string;
};

export type BillingAlert = {
  code: string;
  severity: 'info' | 'warning' | 'error';
  message_key: string;
  message_params?: Record<string, string | number>;
  action_type?: 'checkout_topup' | 'resume_subscription' | 'open_orders';
  action_payload?: Record<string, string | number>;
};

export type BillingTrialOfferStatus =
  | 'disabled'
  | 'ineligible'
  | 'eligible'
  | 'granted';

export type BillingWalletSnapshot = {
  available_credits: number;
  reserved_credits: number;
  lifetime_granted_credits: number;
  lifetime_consumed_credits: number;
};

export type BillingTrialOffer = {
  enabled: boolean;
  status: BillingTrialOfferStatus;
  product_bid: string;
  product_code: string;
  display_name: string;
  description: string;
  currency: string;
  price_amount: number;
  credit_amount: number;
  highlights?: string[];
  valid_days: number;
  starts_on_first_grant: boolean;
  granted_at: string | null;
  expires_at: string | null;
  welcome_dialog_acknowledged_at?: string | null;
};

export type BillingTrialWelcomeAckResult = {
  acknowledged: boolean;
  acknowledged_at: string | null;
};

export type BillingSubscriptionProduct = BillingPlan | BillingTrialOffer;

export type CreatorBillingOverview = {
  creator_bid: string;
  wallet: BillingWalletSnapshot;
  subscription: BillingSubscription | null;
  billing_alerts: BillingAlert[];
  trial_offer: BillingTrialOffer;
};

export type BillingOrderSummary = {
  bill_order_bid: string;
  creator_bid: string;
  product_bid: string;
  subscription_bid: string | null;
  order_type: BillingOrderType;
  status: BillingOrderStatus;
  payment_provider: BillingProvider;
  payment_mode: BillingPaymentMode;
  payable_amount: number;
  paid_amount: number;
  currency: string;
  provider_reference_id: string;
  failure_message?: string;
  created_at: string;
  paid_at: string | null;
};

export type BillingCheckoutResult = {
  bill_order_bid: string;
  provider: BillingProvider;
  payment_mode: BillingPaymentMode;
  status: 'init' | 'pending' | 'paid' | 'failed' | 'unsupported';
  redirect_url?: string;
  checkout_session_id?: string;
  payment_payload?: Record<string, unknown>;
};

export type BillingSyncResult = {
  bill_order_bid: string;
  status: BillingOrderStatus;
};

export type BillingEntitlements = {
  branding_enabled: boolean;
  custom_domain_enabled: boolean;
  priority_class: BillingPriorityClass;
  analytics_tier: BillingAnalyticsTier;
  support_tier: BillingSupportTier;
};

export type BillingDomainBinding = {
  domain_binding_bid: string;
  creator_bid: string;
  host: string;
  status: BillingDomainBindingStatus;
  verification_method: BillingDomainVerificationMethod;
  verification_token: string;
  verification_record_name: string;
  verification_record_value: string;
  last_verified_at: string | null;
  ssl_status: BillingDomainSslStatus;
  is_effective: boolean;
  metadata?: Record<string, unknown>;
};

export type BillingUsageType = 'llm' | 'tts';

export type BillingDailyUsageMetricItem = {
  daily_usage_metric_bid: string;
  stat_date: string;
  shifu_bid: string;
  usage_scene: BillingUsageScene;
  usage_type: BillingUsageType;
  provider: string;
  model: string;
  billing_metric: BillingMetricName;
  raw_amount: number;
  record_count: number;
  consumed_credits: number;
  window_started_at: string;
  window_ended_at: string;
};

export type BillingDailyLedgerSummaryItem = {
  daily_ledger_summary_bid: string;
  stat_date: string;
  entry_type: BillingLedgerEntryType;
  source_type: BillingBucketSourceType;
  amount: number;
  entry_count: number;
  window_started_at: string;
  window_ended_at: string;
};

export type BillingRenewalEventSummary = {
  renewal_event_bid: string;
  event_type: BillingRenewalEventType;
  status: BillingRenewalEventStatus;
  scheduled_at: string | null;
  processed_at: string | null;
  attempt_count: number;
  last_error: string;
  payload?: Record<string, unknown> | null;
};

export type AdminBillingEntitlementSourceKind =
  | 'snapshot'
  | 'product_payload'
  | 'default';

export type AdminBillingSubscriptionItem = BillingSubscription & {
  creator_bid: string;
  next_product_code?: string;
  wallet: BillingWalletSnapshot;
  latest_renewal_event: BillingRenewalEventSummary | null;
  has_attention: boolean;
};

export type AdminBillingOrderItem = BillingOrderSummary & {
  failure_code?: string;
  failed_at?: string | null;
  refunded_at?: string | null;
  has_attention: boolean;
};

export type AdminBillingEntitlementItem = BillingEntitlements & {
  creator_bid: string;
  source_kind: AdminBillingEntitlementSourceKind;
  source_type: BillingBucketSourceType | '';
  source_bid: string;
  product_bid: string;
  effective_from: string | null;
  effective_to: string | null;
  feature_payload?: Record<string, unknown>;
};

export type AdminBillingDomainBindingItem = BillingDomainBinding & {
  custom_domain_enabled: boolean;
  has_attention: boolean;
};

export type AdminBillingDailyUsageMetricItem = BillingDailyUsageMetricItem & {
  creator_bid: string;
};

export type AdminBillingDailyLedgerSummaryItem =
  BillingDailyLedgerSummaryItem & {
    creator_bid: string;
  };

export type AdminBillingLedgerAdjustPayload = {
  creator_bid: string;
  amount: string;
  note?: string;
};

export type AdminBillingLedgerAdjustResult = {
  status: 'adjusted' | 'noop';
  adjustment_bid?: string;
  creator_bid: string;
  amount: number;
  wallet?: {
    wallet_bid: string;
    available_credits: number;
    reserved_credits: number;
  };
  wallet_bucket_bids?: string[];
  ledger_bids?: string[];
};
