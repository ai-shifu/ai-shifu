import { useEffect, useRef } from 'react';
import api from '@/api';
import type { BillingOrderStatus, BillingSyncResult } from '@/types/billing';

const BILLING_PINGXX_POLL_INTERVAL_MS = 1000;
const BILLING_PINGXX_TERMINAL_STATUSES = new Set<BillingOrderStatus>([
  'paid',
  'failed',
  'refunded',
  'canceled',
  'timeout',
]);

type UseBillingPingxxPollingOptions = {
  open: boolean;
  billingOrderBid: string;
  onResolved?: (result: BillingSyncResult) => void | Promise<void>;
};

export function useBillingPingxxPolling({
  open,
  billingOrderBid,
  onResolved,
}: UseBillingPingxxPollingOptions): void {
  const onResolvedRef = useRef(onResolved);
  const inFlightRef = useRef(false);

  useEffect(() => {
    onResolvedRef.current = onResolved;
  }, [onResolved]);

  useEffect(() => {
    if (!open || !billingOrderBid) {
      inFlightRef.current = false;
      return;
    }

    let cancelled = false;

    const pollOrderStatus = async () => {
      if (cancelled || inFlightRef.current) {
        return;
      }

      inFlightRef.current = true;
      try {
        const result = (await api.syncBillingOrder({
          bill_order_bid: billingOrderBid,
        })) as BillingSyncResult;
        if (!cancelled && BILLING_PINGXX_TERMINAL_STATUSES.has(result.status)) {
          await onResolvedRef.current?.(result);
        }
      } catch {
        // Keep polling while the dialog is open; transient sync failures should
        // not permanently block payment completion from surfacing.
      } finally {
        inFlightRef.current = false;
      }
    };

    const timer = window.setInterval(
      () => void pollOrderStatus(),
      BILLING_PINGXX_POLL_INTERVAL_MS,
    );

    return () => {
      cancelled = true;
      inFlightRef.current = false;
      window.clearInterval(timer);
    };
  }, [billingOrderBid, open]);
}
