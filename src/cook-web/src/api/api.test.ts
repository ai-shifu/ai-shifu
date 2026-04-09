import api from './api';

describe('billing api definitions', () => {
  test('exposes creator billing endpoints', () => {
    expect(api.getBillingCatalog).toBe('GET /billing/catalog');
    expect(api.getBillingOverview).toBe('GET /billing/overview');
    expect(api.getBillingEntitlements).toBe('GET /billing/entitlements');
    expect(api.getBillingWalletBuckets).toBe('GET /billing/wallet-buckets');
    expect(api.getBillingLedger).toBe('GET /billing/ledger');
    expect(api.getBillingOrders).toBe('GET /billing/orders');
    expect(api.getBillingOrderDetail).toBe(
      'GET /billing/orders/{billing_order_bid}',
    );
    expect(api.syncBillingOrder).toBe(
      'POST /billing/orders/{billing_order_bid}/sync',
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
    expect(api.getAdminBillingDomainBindings).toBe(
      'GET /admin/billing/domain-bindings',
    );
    expect(api.bindAdminBillingDomain).toBe('POST /admin/billing/domains/bind');
    expect(api.adjustAdminBillingLedger).toBe(
      'POST /admin/billing/ledger/adjust',
    );
  });
});
