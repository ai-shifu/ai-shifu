import useSWR from 'swr';
import api from '@/api';
import type { BillingWalletBucketList } from '@/types/billing';

export const BILLING_WALLET_BUCKETS_SWR_KEY = [
  'billing-wallet-buckets',
] as const;

export function useBillingWalletBuckets() {
  return useSWR<BillingWalletBucketList>(
    BILLING_WALLET_BUCKETS_SWR_KEY,
    async () =>
      (await api.getBillingWalletBuckets({})) as BillingWalletBucketList,
    {
      revalidateOnFocus: false,
    },
  );
}
