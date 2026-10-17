import useSWR from 'swr';
import api from '@/api';

export type BillingPaymentProvider = {
  provider: string;
  label_key: string;
  catalog: boolean;
  discounts: boolean;
};

export type BillingPaymentProviders = {
  items: BillingPaymentProvider[];
  discount_sync_required: boolean;
};

/** Administrative capabilities are server-owned and independent of checkout scenes. */
export function useBillingPaymentProviders(enabled = true) {
  return useSWR<BillingPaymentProviders>(
    enabled ? 'admin-billing-payment-providers' : null,
    () => api.getAdminBillingPaymentProviders({}, { skipErrorToast: true }),
    { revalidateOnFocus: false },
  );
}
