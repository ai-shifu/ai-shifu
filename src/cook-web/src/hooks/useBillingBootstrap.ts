import useSWR from 'swr';
import api from '@/api';
import type { BillingBootstrap } from '@/types/billing';

export const BILLING_BOOTSTRAP_SWR_KEY = ['creator-billing-bootstrap'] as const;

export function useBillingBootstrap() {
  return useSWR<BillingBootstrap>(
    BILLING_BOOTSTRAP_SWR_KEY,
    async () => (await api.getBillingBootstrap({})) as BillingBootstrap,
    {
      revalidateOnFocus: false,
    },
  );
}
