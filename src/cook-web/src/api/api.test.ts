import api from './api';

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
