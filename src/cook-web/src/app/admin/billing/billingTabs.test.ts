import { resolveBillingTab } from './billingTabs';

describe('resolveBillingTab', () => {
  test('returns details for the details tab', () => {
    expect(resolveBillingTab('details')).toBe('details');
  });

  test('falls back to packages for missing or unknown tabs', () => {
    expect(resolveBillingTab(undefined)).toBe('packages');
    expect(resolveBillingTab(null)).toBe('packages');
    expect(resolveBillingTab('packages')).toBe('packages');
    expect(resolveBillingTab('unknown')).toBe('packages');
  });
});
