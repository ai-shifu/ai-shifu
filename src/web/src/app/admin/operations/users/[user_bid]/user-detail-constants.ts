import type {
  AdminOperationUserCreditSummary,
  AdminOperationUserCreditsResponse,
  AdminOperationUserDetailResponse,
} from '../../operation-user-types';

export type ErrorState = { message: string; code?: number };
export type DetailTab = 'credits' | 'learning' | 'created';

export const CREDITS_PAGE_SIZE = 10;
export const EMPTY_VALUE = '--';

export const DETAIL_TAB_HASHES: Record<DetailTab, string> = {
  credits: '#credits',
  learning: '#learning-courses',
  created: '#created-courses',
};

export const DEFAULT_CREDIT_SUMMARY: AdminOperationUserCreditSummary = {
  available_credits: '',
  subscription_credits: '',
  topup_credits: '',
  credits_expire_at: '',
  has_active_subscription: false,
};

export const createEmptyCreditsResponse =
  (): AdminOperationUserCreditsResponse => ({
    summary: DEFAULT_CREDIT_SUMMARY,
    items: [],
    page: 1,
    page_count: 0,
    page_size: CREDITS_PAGE_SIZE,
    total: 0,
  });

export const EMPTY_DETAIL: AdminOperationUserDetailResponse = {
  user_bid: '',
  mobile: '',
  email: '',
  nickname: '',
  user_status: 'unknown',
  user_role: 'unknown',
  user_roles: [],
  login_methods: [],
  language: '',
  learning_courses: [],
  learning_course_count: 0,
  created_courses: [],
  created_course_count: 0,
  registration_source: 'unknown',
  total_paid_amount: '0',
  available_credits: '',
  subscription_credits: '',
  topup_credits: '',
  credits_expire_at: '',
  has_active_subscription: false,
  last_login_at: '',
  last_learning_at: '',
  created_at: '',
  updated_at: '',
};

export const resolveDetailTabFromHash = (hash: string): DetailTab | null => {
  const hashEntry = Object.entries(DETAIL_TAB_HASHES).find(
    ([, targetHash]) => targetHash === hash,
  ) as [DetailTab, string] | undefined;

  return hashEntry?.[0] ?? null;
};
