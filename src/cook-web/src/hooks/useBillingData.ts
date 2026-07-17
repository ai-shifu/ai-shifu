import useSWR from 'swr';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { buildBillingSwrKey } from '@/lib/billing';
import type {
  BillingBootstrap,
  BillingWalletBucketList,
  CreatorBillingOverview,
  BillingCustomization,
} from '@/types/billing';

const BILLING_SWR_OPTIONS = {
  revalidateOnFocus: false,
} as const;

const BILLING_PASSIVE_REQUEST_CONFIG = {
  skipErrorToast: true,
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

  return useSWR<CreatorBillingOverview>(
    billingEnabled ? buildBillingSwrKey(BILLING_OVERVIEW_SWR_KEY) : null,
    async () =>
      (await api.getBillingOverview(
        {},
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as CreatorBillingOverview,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingWalletBuckets() {
  const billingEnabled = useBillingEnabled();

  return useSWR<BillingWalletBucketList>(
    billingEnabled ? buildBillingSwrKey(BILLING_WALLET_BUCKETS_SWR_KEY) : null,
    async () =>
      (await api.getBillingWalletBuckets(
        {},
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingWalletBucketList,
    BILLING_SWR_OPTIONS,
  );
}

export function useBillingCustomization() {
  const billingEnabled = useBillingEnabled();
  return useSWR<BillingCustomization>(
    billingEnabled ? buildBillingSwrKey('billing-customization') : null,
    async () =>
      (await api.getBillingCustomization(
        {},
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingCustomization,
    BILLING_SWR_OPTIONS,
  );
}
