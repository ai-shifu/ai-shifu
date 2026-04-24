export type BillingTab = 'packages' | 'details';

export function resolveBillingTab(tab?: string | null): BillingTab {
  return tab === 'details' ? 'details' : 'packages';
}
