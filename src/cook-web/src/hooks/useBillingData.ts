import useSWR from 'swr';
import api from '@/api';
import { buildBillingSwrKey, withBillingTimezone } from '@/lib/billing';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import type {
  BillingBootstrap,
  BillingWalletBucketList,
  CreatorBillingOverview,
} from '@/types/billing';

const BILLING_SWR_OPTIONS = {
  revalidateOnFocus: false,
} as const;

export const BILLING_BOOTSTRAP_SWR_KEY = ['creator-billing-bootstrap'] as const;
export const BILLING_OVERVIEW_SWR_KEY = 'creator-billing-overview';
export const BILLING_WALLET_BUCKETS_SWR_KEY = 'billing-wallet-buckets';

export function useBillingBootstrap() {
  return useSWR<BillingBootstrap>(
    BILLING_BOOTSTRAP_SWR_KEY,
    async () => (await api.getBillingBootstrap({})) as BillingBootstrap,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingOverview() {
  const timezone = getBrowserTimeZone();

  return useSWR<CreatorBillingOverview>(
    buildBillingSwrKey(BILLING_OVERVIEW_SWR_KEY, timezone),
    async () =>
      (await api.getBillingOverview(
        withBillingTimezone({}, timezone),
      )) as CreatorBillingOverview,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingWalletBuckets() {
  const timezone = getBrowserTimeZone();

  return useSWR<BillingWalletBucketList>(
    buildBillingSwrKey(BILLING_WALLET_BUCKETS_SWR_KEY, timezone),
    async () =>
      (await api.getBillingWalletBuckets(
        withBillingTimezone({}, timezone),
      )) as BillingWalletBucketList,
    BILLING_SWR_OPTIONS,
  );
}
