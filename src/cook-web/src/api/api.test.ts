import api from './api';

describe('auth api definitions', () => {
  test('exposes captcha and SMS login endpoints', () => {
    expect(api.getCaptcha).toBe('GET /user/captcha');
    expect(api.verifyCaptcha).toBe('POST /user/captcha/verify');
    expect(api.sendSmsCode).toBe('POST /user/send_sms_code');
    expect(api.smsLogin).toBe('POST /user/login_sms');
    expect(Object.prototype.hasOwnProperty.call(api, 'verifySmsCode')).toBe(
      false,
    );
  });

  test('exposes admin onboarding endpoints', () => {
    expect(api.getCreatorOnboardingStatus).toBe('GET /user/onboarding/status');
    expect(api.completeCreatorOnboarding).toBe(
      'POST /user/onboarding/complete',
    );
  });
});

describe('profile onboarding api definitions', () => {
  test('exposes learner and operator profile onboarding endpoints', () => {
    expect(api.getProfileOnboarding).toBe('GET /user/profile-onboarding');
    expect(api.completeProfileOnboarding).toBe(
      'POST /user/profile-onboarding/complete',
    );
    expect(api.getAdminOperationProfileOnboardingConfig).toBe(
      'GET /shifu/admin/operations/profile-onboarding',
    );
    expect(api.updateAdminOperationProfileOnboardingConfig).toBe(
      'POST /shifu/admin/operations/profile-onboarding',
    );
  });
});

describe('operator voice clone api definitions', () => {
  test('exposes operator MiniMax voice clone record endpoint', () => {
    expect(api.getAdminOperationVoiceClones).toBe(
      'GET /shifu/admin/operations/voice-clones',
    );
  });
});

describe('referral api definitions', () => {
  test('exposes creator and anonymous referral endpoints', () => {
    expect(api.getReferralInviteProfile).toBe('GET /referral/invite-profile');
    expect(api.getReferralInvitePreview).toBe('GET /referral/invite-preview');
    expect(api.recordReferralInviteEvent).toBe('POST /referral/invite-event');
  });

  test('exposes operator referral endpoints', () => {
    expect(api.getAdminOperationReferrals).toBe(
      'GET /shifu/admin/operations/referrals',
    );
    expect(api.getAdminOperationReferralsOverview).toBe(
      'GET /shifu/admin/operations/referrals/overview',
    );
    expect(api.getAdminOperationReferralDetail).toBe(
      'GET /shifu/admin/operations/referrals/{relation_bid}',
    );
    expect(api.updateAdminOperationReferralStatus).toBe(
      'POST /shifu/admin/operations/referrals/{relation_bid}/status',
    );
    expect(api.adjustAdminOperationReferral).toBe(
      'POST /shifu/admin/operations/referrals/{relation_bid}/adjustment',
    );
  });

  test('exposes operator referral campaign promotion endpoints', () => {
    expect(api.getAdminOperationPromotionReferralCampaigns).toBe(
      'GET /shifu/admin/operations/promotions/referral-campaigns',
    );
    expect(api.createAdminOperationPromotionReferralCampaign).toBe(
      'POST /shifu/admin/operations/promotions/referral-campaigns',
    );
    expect(api.getAdminOperationPromotionReferralCampaignDetail).toBe(
      'GET /shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}',
    );
    expect(api.updateAdminOperationPromotionReferralCampaign).toBe(
      'POST /shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}',
    );
    expect(api.updateAdminOperationPromotionReferralCampaignStatus).toBe(
      'POST /shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}/status',
    );
  });
});

describe('billing api definitions', () => {
  test('exposes creator billing endpoints', () => {
    expect(api.getBillingBootstrap).toBe('GET /billing');
    expect(api.getBillingCatalog).toBe('GET /billing/catalog');
    expect(api.getBillingOverview).toBe('GET /billing/overview');
    expect(api.acknowledgeBillingTrialWelcome).toBe(
      'POST /billing/trial-offer/welcome/ack',
    );
    expect(api.getBillingWalletBuckets).toBe('GET /billing/wallet-buckets');
    expect(api.getBillingLedger).toBe('GET /billing/ledger');
    expect(api.checkoutBillingOrder).toBe(
      'POST /billing/orders/{bill_order_bid}/checkout',
    );
    expect(api.syncBillingOrder).toBe(
      'POST /billing/orders/{bill_order_bid}/sync',
    );
    expect(api.checkoutBillingSubscription).toBe(
      'POST /billing/subscriptions/checkout',
    );
    expect(api.cancelBillingSubscription).toBe(
      'POST /billing/subscriptions/cancel',
    );
    expect(api.resumeBillingSubscription).toBe(
      'POST /billing/subscriptions/resume',
    );
    expect(api.checkoutBillingTopup).toBe('POST /billing/topups/checkout');
  });

  test('exposes admin billing endpoints', () => {
    expect(api.getAdminBillingSubscriptions).toBe(
      'GET /admin/billing/subscriptions',
    );
    expect(api.getAdminBillingCampaignProductOptions).toBe(
      'GET /admin/billing/products/options',
    );
    expect(api.getAdminBillingCampaigns).toBe('GET /admin/billing/campaigns');
    expect(api.createAdminBillingCampaign).toBe(
      'POST /admin/billing/campaigns',
    );
    expect(api.getAdminBillingCampaignDetail).toBe(
      'GET /admin/billing/campaigns/{campaign_bid}',
    );
    expect(api.updateAdminBillingCampaign).toBe(
      'POST /admin/billing/campaigns/{campaign_bid}',
    );
    expect(api.updateAdminBillingCampaignStatus).toBe(
      'POST /admin/billing/campaigns/{campaign_bid}/status',
    );
    expect(api.getAdminBillingOrders).toBe('GET /admin/billing/orders');
    expect(api.getAdminBillingEntitlements).toBe(
      'GET /admin/billing/entitlements',
    );
    expect(api.getAdminBillingDomainAudits).toBe(
      'GET /admin/billing/domain-audits',
    );
    expect(api.getAdminBillingDailyUsageMetrics).toBe(
      'GET /admin/billing/reports/usage-daily',
    );
    expect(api.getAdminBillingDailyLedgerSummary).toBe(
      'GET /admin/billing/reports/ledger-daily',
    );
    expect(api.adjustAdminBillingLedger).toBe(
      'POST /admin/billing/ledger/adjust',
    );
  });
});
