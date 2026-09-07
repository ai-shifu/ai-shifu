import {
  buildLoginAttemptAnalytics,
  buildLoginResultAnalytics,
} from './loginAnalytics';

describe('login analytics payloads', () => {
  it('uses bounded methods without identity data', () => {
    expect(buildLoginAttemptAnalytics('password')).toEqual({
      login_method: 'password',
    });
    expect(buildLoginAttemptAnalytics('email')).toEqual({
      login_method: 'email',
    });
  });

  it('adds only a bounded failure category to failed results', () => {
    expect(buildLoginResultAnalytics('sms', 'success')).toEqual({
      login_method: 'sms',
      outcome: 'success',
    });
    expect(
      buildLoginResultAnalytics('sms', 'failed', 'credentials_rejected'),
    ).toEqual({
      login_method: 'sms',
      outcome: 'failed',
      failure_category: 'credentials_rejected',
    });
  });
});
