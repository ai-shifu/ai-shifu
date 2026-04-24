import useSWR from 'swr';
import api from '@/api';
import { useEnvStore } from '@/c-store';
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

const BILLING_BOOTSTRAP_SWR_KEY = ['creator-billing-bootstrap'] as const;
export const BILLING_OVERVIEW_SWR_KEY = 'creator-billing-overview';
export const BILLING_WALLET_BUCKETS_SWR_KEY = 'billing-wallet-buckets';

function useBillingEnabled(): boolean {
  return useEnvStore(state => state.billingEnabled === 'true');
}

export function useBillingBootstrap() {
  const billingEnabled = useBillingEnabled();

  return useSWR<BillingBootstrap>(
    billingEnabled ? BILLING_BOOTSTRAP_SWR_KEY : null,
    async () => (await api.getBillingBootstrap({})) as BillingBootstrap,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingOverview() {
  const billingEnabled = useBillingEnabled();
  const timezone = getBrowserTimeZone();

  return useSWR<CreatorBillingOverview>(
    billingEnabled
      ? buildBillingSwrKey(BILLING_OVERVIEW_SWR_KEY, timezone)
      : null,
    async () =>
      (await api.getBillingOverview(
        withBillingTimezone({}, timezone),
      )) as CreatorBillingOverview,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingWalletBuckets() {
  const billingEnabled = useBillingEnabled();
  const timezone = getBrowserTimeZone();

  return useSWR<BillingWalletBucketList>(
    billingEnabled
      ? buildBillingSwrKey(BILLING_WALLET_BUCKETS_SWR_KEY, timezone)
      : null,
    async () =>
      (await api.getBillingWalletBuckets(
        withBillingTimezone({}, timezone),
      )) as BillingWalletBucketList,
    BILLING_SWR_OPTIONS,
  );
}
