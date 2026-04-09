export type BillingCenterTab =
  | 'plans'
  | 'ledger'
  | 'orders'
  | 'entitlements'
  | 'domains'
  | 'reports';

export type AdminBillingConsoleTab = 'subscriptions' | 'orders' | 'exceptions';

export type BillingProvider = 'stripe' | 'pingxx';

export type BillingPaymentMode = 'subscription' | 'one_time';

export type BillingPlanInterval = 'month' | 'year';

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

export type BillingBucketCategory = 'free' | 'subscription' | 'topup';

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

export type BillingMetricBreakdownItem = {
  billing_metric: BillingMetricName;
  raw_amount: number;
  unit_size: number;
  credits_per_unit: number;
  rounding_mode: BillingRoundingMode;
  consumed_credits: number;
};

export type BillingLedgerMetadata = {
  usage_bid?: string;
  usage_scene?: BillingUsageScene;
  provider?: string;
  model?: string;
  metric_breakdown?: BillingMetricBreakdownItem[];
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

export type BillingWalletSnapshot = {
  available_credits: number;
  reserved_credits: number;
  lifetime_granted_credits: number;
  lifetime_consumed_credits: number;
};

export type CreatorBillingOverview = {
  creator_bid: string;
  wallet: BillingWalletSnapshot;
  subscription: BillingSubscription | null;
  billing_alerts: BillingAlert[];
};

export type BillingOrderSummary = {
  billing_order_bid: string;
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

export type BillingOrderDetail = BillingOrderSummary & {
  metadata?: Record<string, unknown> | null;
  failure_code?: string;
  refunded_at?: string | null;
  failed_at?: string | null;
};

export type BillingCheckoutResult = {
  billing_order_bid: string;
  provider: BillingProvider;
  payment_mode: BillingPaymentMode;
  status: 'init' | 'pending' | 'paid' | 'failed' | 'unsupported';
  redirect_url?: string;
  checkout_session_id?: string;
  payment_payload?: Record<string, unknown>;
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
