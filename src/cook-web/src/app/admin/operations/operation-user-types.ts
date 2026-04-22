type LooseString = string & {};

export type AdminOperationUserCourseItem = {
  shifu_bid: string;
  course_name: string;
  course_status: 'published' | 'unpublished' | LooseString;
  completed_lesson_count: number;
  total_lesson_count: number;
};

export type AdminOperationUserItem = {
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  user_status: 'unregistered' | 'registered' | 'paid' | 'unknown' | LooseString;
  user_role:
    | 'regular'
    | 'creator'
    | 'operator'
    | 'learner'
    | 'unknown'
    | LooseString;
  user_roles: string[];
  login_methods: string[];
  registration_source:
    | 'phone'
    | 'email'
    | 'google'
    | 'wechat'
    | 'imported'
    | 'unknown'
    | LooseString;
  language: string;
  learning_courses: AdminOperationUserCourseItem[];
  created_courses: AdminOperationUserCourseItem[];
  total_paid_amount: string;
  available_credits: string;
  subscription_credits: string;
  topup_credits: string;
  credits_expire_at: string;
  has_active_subscription: boolean;
  last_login_at: string;
  last_learning_at: string;
  created_at: string;
  updated_at: string;
};

export type AdminOperationUserListResponse = {
  items: AdminOperationUserItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type AdminOperationUserDetailResponse = AdminOperationUserItem;

export type AdminOperationUserCreditSummary = {
  available_credits: string;
  subscription_credits: string;
  topup_credits: string;
  credits_expire_at: string;
  has_active_subscription: boolean;
};

export type AdminOperationUserCreditLedgerItem = {
  ledger_bid: string;
  created_at: string;
  entry_type: string;
  source_type: string;
  display_entry_type: string;
  display_source_type: string;
  amount: string;
  balance_after: string;
  expires_at: string;
  consumable_from: string;
  note: string;
  note_code: string;
};

export type AdminOperationUserCreditsResponse = {
  summary: AdminOperationUserCreditSummary;
  items: AdminOperationUserCreditLedgerItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type AdminOperationUserCreditGrantRequest = {
  request_id: string;
  amount: string;
  grant_source: string;
  validity_preset: string;
  note?: string;
};

export type AdminOperationUserCreditGrantResponse = {
  user_bid: string;
  amount: string;
  grant_source: string;
  validity_preset: string;
  expires_at: string;
  wallet_bucket_bid: string;
  ledger_bid: string;
  summary: AdminOperationUserCreditSummary;
};
