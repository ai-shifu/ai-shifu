export type LoginMethod = 'password' | 'sms' | 'google';
export type LoginFailureCategory =
  | 'credentials_rejected'
  | 'request_failed'
  | 'start_failed'
  | 'callback_invalid'
  | 'callback_failed';

export const buildLoginAttemptAnalytics = (loginMethod: LoginMethod) => ({
  login_method: loginMethod,
});

export const buildLoginResultAnalytics = (
  loginMethod: LoginMethod,
  outcome: 'success' | 'failed',
  failureCategory?: LoginFailureCategory,
) => ({
  login_method: loginMethod,
  outcome,
  ...(outcome === 'failed' && failureCategory
    ? { failure_category: failureCategory }
    : {}),
});
