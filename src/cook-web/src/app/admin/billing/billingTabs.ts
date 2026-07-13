export type BillingTab = 'packages' | 'details' | 'customization';

export function resolveBillingTab(tab?: string | null): BillingTab {
  return tab === 'details' || tab === 'customization' ? tab : 'packages';
}
