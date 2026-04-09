import useSWR from 'swr';
import api from '@/api';
import type { BillingEntitlements } from '@/types/billing';

export const BILLING_ENTITLEMENTS_SWR_KEY = [
  'creator-billing-entitlements',
] as const;

export function useBillingEntitlements() {
  return useSWR<BillingEntitlements>(
    BILLING_ENTITLEMENTS_SWR_KEY,
    async () => (await api.getBillingEntitlements({})) as BillingEntitlements,
    {
      revalidateOnFocus: false,
    },
  );
}
