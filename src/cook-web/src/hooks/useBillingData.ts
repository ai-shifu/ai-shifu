import useSWR from 'swr';
import api from '@/api';
import type {
  BillingBootstrap,
  BillingEntitlements,
  BillingWalletBucketList,
  CreatorBillingOverview,
} from '@/types/billing';

const BILLING_SWR_OPTIONS = {
  revalidateOnFocus: false,
} as const;

export const BILLING_BOOTSTRAP_SWR_KEY = ['creator-billing-bootstrap'] as const;
export const BILLING_OVERVIEW_SWR_KEY = ['creator-billing-overview'] as const;
export const BILLING_ENTITLEMENTS_SWR_KEY = [
  'creator-billing-entitlements',
] as const;
export const BILLING_WALLET_BUCKETS_SWR_KEY = [
  'billing-wallet-buckets',
] as const;

export function useBillingBootstrap() {
  return useSWR<BillingBootstrap>(
    BILLING_BOOTSTRAP_SWR_KEY,
    async () => (await api.getBillingBootstrap({})) as BillingBootstrap,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingOverview() {
  return useSWR<CreatorBillingOverview>(
    BILLING_OVERVIEW_SWR_KEY,
    async () => (await api.getBillingOverview({})) as CreatorBillingOverview,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingEntitlements() {
  return useSWR<BillingEntitlements>(
    BILLING_ENTITLEMENTS_SWR_KEY,
    async () => (await api.getBillingEntitlements({})) as BillingEntitlements,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingWalletBuckets() {
  return useSWR<BillingWalletBucketList>(
    BILLING_WALLET_BUCKETS_SWR_KEY,
    async () =>
      (await api.getBillingWalletBuckets({})) as BillingWalletBucketList,
    BILLING_SWR_OPTIONS,
  );
}
