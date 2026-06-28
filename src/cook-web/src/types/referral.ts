export type ReferralEntrySource = 'invite_link' | 'manual_code';

export type ReferralLoginMetadata = {
  invite_code?: string;
  referral_session_id?: string;
  referral_entry_source?: ReferralEntrySource;
};

export type ReferralRewardQueueItem = {
  queue_index: number;
  reward_bid: string;
  relation_bid: string;
  invitee_mobile_snapshot: string;
  reward_status: number;
  reward_credit_amount: string | null;
  reward_product_code: string;
  ledger_credit_state: string;
  effective_at: string | null;
  expires_at: string | null;
  created_at: string | null;
};

export type ReferralInviteProfile = {
  available?: boolean;
  campaign_bid: string;
  campaign_code: string;
  invite_code: string;
  invite_url: string;
  reward_product_code: string;
  reward_cycle_count: number;
  reward_credit_amount: string | null;
  reward_credit_validity_days: number | null;
  reward_cap_scope: string;
  reward_cap_count: number | null;
  reward_granted_count: number;
  reward_remaining_count: number | null;
  reward_queue_summary: Record<string, number>;
  reward_queue?: ReferralRewardQueueItem[];
  rules_copy_i18n_key?: string;
};

export type ReferralInvitePreview = {
  recognized: boolean;
  invite_code: string;
  inviter_mobile_masked: string;
};

export type ReferralInviteEventType =
  | 'invite_link_clicked'
  | 'registration_page_viewed'
  | 'invite_code_entered'
  | 'registration_submitted';

export type ReferralInviteEventPayload = {
  event_type: ReferralInviteEventType;
  invite_code?: string;
  landing_path?: string;
  session_id?: string;
  frontend_session_id?: string;
  entry_source?: ReferralEntrySource;
};

export type ReferralInviteEventResponse = {
  success: boolean;
  session_id: string;
  recognized: boolean;
};

export type AdminReferralUserSummary = {
  user_bid?: string;
  nickname?: string;
  identifier?: string;
};

export type AdminReferralReward = {
  reward_bid: string;
  reward_status: number;
  reward_target: string;
  reward_type: string;
  reward_product_code: string;
  reward_cycle_count: number;
  reward_credit_amount: string | null;
  reward_credit_validity_days: number | null;
  reward_cap_scope: string;
  reward_cap_count: number | null;
  reward_timing_policy: string;
  rule_snapshot: Record<string, unknown>;
  billing_artifacts: Record<string, unknown>;
  operator_note: string;
  effective_at: string | null;
  expires_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AdminReferralRewardQueueItem = {
  queue_index: number;
  reward_bid: string;
  relation_bid: string;
  invitee_user_bid: string;
  invitee_mobile_snapshot: string;
  reward_status: number;
  reward_credit_amount: string | null;
  reward_product_code: string;
  bill_order_bid: string;
  subscription_bid: string;
  wallet_bucket_bid: string;
  ledger_bid: string;
  ledger_credit_state: string;
  effective_at: string | null;
  expires_at: string | null;
  created_at: string | null;
};

export type AdminReferralRelation = {
  relation_bid: string;
  campaign_bid: string;
  campaign_code: string;
  campaign_name: string;
  reward_rule_bid: string;
  invite_code: string;
  inviter_user_bid: string;
  inviter: AdminReferralUserSummary;
  invitee_user_bid: string;
  invitee: AdminReferralUserSummary;
  invitee_mobile_snapshot: string;
  bound_at: string | null;
  registration_source: string;
  reward_eligible: boolean;
  relation_status: number;
  abnormal_status: number;
  metadata: Record<string, unknown>;
  reward: AdminReferralReward | null;
  reward_queue?: AdminReferralRewardQueueItem[];
  created_at: string | null;
  updated_at: string | null;
};

export type AdminReferralListResponse = {
  items: AdminReferralRelation[];
  page_index: number;
  page_size: number;
  total: number;
};

export type AdminReferralOverview = {
  total_relations: number;
  abnormal_relations: number;
  generated_rewards: number;
};

export type AdminReferralStatusPayload = {
  relation_status?: 'abnormal_reviewing' | 'canceled';
  abnormal_status?: 'normal' | 'reviewing' | 'confirmed_abnormal';
  reward_status?: 'frozen' | 'canceled';
  operator_note?: string;
};

export const REFERRAL_RELATION_STATUS = {
  registered: 7831,
  rewardGenerated: 7832,
  rewardPendingEffective: 7833,
  rewardActive: 7834,
  rewardEnded: 7835,
  rewardSkippedCap: 7836,
  abnormalReviewing: 7837,
  canceled: 7838,
} as const;

export const REFERRAL_ABNORMAL_STATUS = {
  normal: 7841,
  reviewing: 7842,
  confirmedAbnormal: 7843,
} as const;

export const REFERRAL_REWARD_STATUS = {
  generated: 7851,
  pendingEffective: 7852,
  active: 7853,
  expired: 7854,
  frozen: 7855,
  canceled: 7856,
  skippedCap: 7857,
} as const;
