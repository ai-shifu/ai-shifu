import { useEffect, useRef } from 'react';
import { useTracking } from './useTracking';
import {
  normalizeLearnerPaymentChannel,
  trackLearnerPaymentEventSafely,
} from '@/lib/paymentAnalytics';

type Props = {
  open: boolean;
  isLoggedIn: boolean;
  previewMode: boolean;
  shifuBid: string;
  orderId: string;
  channel: string;
  surface: 'desktop' | 'mobile';
  reason?: 'unsupported_contract' | 'unsupported_action';
};

/** Measure client/payment-contract incompatibility without changing payment state. */
export function usePaymentActionUnavailableTracking({
  open,
  isLoggedIn,
  previewMode,
  shifuBid,
  orderId,
  channel,
  surface,
  reason,
}: Props) {
  const { trackEvent } = useTracking();
  const reported = useRef(new Set<string>());
  useEffect(() => {
    if (!open) {
      reported.current.clear();
      return;
    }
    if (!isLoggedIn || previewMode || !shifuBid || !orderId || !reason) return;
    const normalizedChannel = normalizeLearnerPaymentChannel(channel);
    const key = `${orderId}:${normalizedChannel}:${reason}`;
    if (reported.current.has(key)) return;
    reported.current.add(key);
    trackLearnerPaymentEventSafely(
      trackEvent,
      'learner_payment_action_unavailable',
      {
        shifu_bid: shifuBid,
        order_id: orderId,
        channel: normalizedChannel,
        surface,
        reason,
      },
    );
  }, [
    channel,
    isLoggedIn,
    open,
    orderId,
    previewMode,
    reason,
    shifuBid,
    surface,
    trackEvent,
  ]);
}
