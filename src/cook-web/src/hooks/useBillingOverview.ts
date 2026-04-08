import useSWR from 'swr';
import api from '@/api';
import type { CreatorBillingOverview } from '@/types/billing';

export const BILLING_OVERVIEW_SWR_KEY = ['creator-billing-overview'] as const;

export function useBillingOverview() {
  return useSWR<CreatorBillingOverview>(
    BILLING_OVERVIEW_SWR_KEY,
    async () => (await api.getBillingOverview({})) as CreatorBillingOverview,
    {
      revalidateOnFocus: false,
    },
  );
}
