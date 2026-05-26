type LooseString = string & {};

export type CreditNotificationType =
  | 'credit_expiring'
  | 'credit_granted'
  | 'low_balance'
  | LooseString;

export type CreditNotificationStatus =
  | 'pending'
  | 'sent'
  | 'skipped_no_mobile'
  | 'skipped_opt_out'
  | 'suppressed_duplicate'
  | 'failed_provider'
  | LooseString;

export type AdminOperationCreditNotificationItem = {
  notification_bid: string;
  notification_type: CreditNotificationType;
  channel: string;
  creator_bid: string;
  target_user_bid: string;
  mobile_snapshot: string;
  source_type: string;
  source_bid: string;
  dedupe_key: string;
  status: CreditNotificationStatus;
  template_code: string;
  template_params: Record<string, unknown>;
  policy_snapshot: Record<string, unknown>;
  provider_response: Record<string, unknown>;
  error_code: string;
  error_message: string;
  requested_at: string;
  attempted_at: string;
  sent_at: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type AdminOperationCreditNotificationListResponse = {
  items: AdminOperationCreditNotificationItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type AdminOperationCreditNotificationDryRunResponse = {
  status: string;
  candidate_count: number;
  created_count: number;
  dry_run: boolean;
  notifications: Array<Record<string, unknown>>;
  sections?: Record<string, unknown>;
};

export type AdminOperationCreditNotificationRequeueResponse = {
  status: string;
  notification_bid?: string;
  notification_status?: string;
  enqueued?: boolean;
  message?: string;
};

export type AdminOperationCreditNotificationTemplateSyncRequest = {
  notification_type: CreditNotificationType;
  template_code: string;
};

export type AdminOperationCreditNotificationTemplateSyncResponse = {
  notification_template_bid?: string;
  notification_type: CreditNotificationType;
  channel: string;
  provider: string;
  template_code: string;
  template_name: string;
  template_content: string;
  template_status: string;
  template_type: string;
  variable_attribute: string | Record<string, unknown>;
  provider_response: Record<string, unknown>;
  placeholders: string[];
  supported_placeholders: string[];
  unused_supported_placeholders: string[];
  unsupported_placeholders: string[];
  sync_status: string;
  error_code: string;
  error_message: string;
  last_synced_at: string;
  compatible: boolean;
};

export type CreditNotificationFixedThreshold = {
  kind: 'fixed';
  value: string;
};

export type CreditNotificationEstimatedDaysThreshold = {
  kind: 'estimated_days';
  days: number;
  lookback_days: number;
  min_consumed_days: number;
  fallback_fixed_value?: string;
};

export type CreditNotificationThreshold =
  | CreditNotificationFixedThreshold
  | CreditNotificationEstimatedDaysThreshold;

export type CreditNotificationTypePolicy = {
  enabled: boolean;
  template_code: string;
  windows?: string[];
  merge_same_creator?: boolean;
  thresholds?: CreditNotificationThreshold[];
};

export type AdminOperationCreditNotificationPolicy = {
  enabled: boolean;
  channel: 'sms';
  types: {
    credit_expiring: CreditNotificationTypePolicy;
    credit_granted: CreditNotificationTypePolicy;
    low_balance: CreditNotificationTypePolicy;
  };
  softlimit: {
    enabled: boolean;
    threshold: CreditNotificationFixedThreshold;
    teacher_page_alert: boolean;
    disable_debug: boolean;
    sms_enabled: boolean;
  };
  frequency: {
    per_mobile_per_day: number;
    per_creator_per_type_per_day: number;
  };
  quiet_hours: {
    enabled: boolean;
    start: string;
    end: string;
    timezone: string;
  };
  blacklist: {
    creator_bids: string[];
    mobiles: string[];
  };
  opt_out: {
    creator_bids: string[];
    mobiles: string[];
  };
  budget: {
    daily_sms_limit: number;
    dry_run_required: boolean;
    sms_unit_cost: string;
  };
};
