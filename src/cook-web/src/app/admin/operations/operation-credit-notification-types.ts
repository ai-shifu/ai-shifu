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
