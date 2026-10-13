import { renderHook } from '@testing-library/react';
import { usePaymentActionUnavailableTracking } from './usePaymentActionUnavailableTracking';

const trackEvent = jest.fn();
jest.mock('./useTracking', () => ({ useTracking: () => ({ trackEvent }) }));

const props = {
  open: true,
  isLoggedIn: true,
  previewMode: false,
  shifuBid: 'course',
  orderId: 'order',
  channel: 'alipay_qr',
  surface: 'desktop' as const,
  reason: 'unsupported_action' as const,
};

beforeEach(() => trackEvent.mockReset());

test('reports the exact safe payload after an eligible exposure and deduplicates rerenders', () => {
  const { rerender } = renderHook(
    value => usePaymentActionUnavailableTracking(value),
    { initialProps: props },
  );
  expect(trackEvent).toHaveBeenCalledWith(
    'learner_payment_action_unavailable',
    {
      shifu_bid: 'course',
      order_id: 'order',
      channel: 'alipay_qr',
      surface: 'desktop',
      reason: 'unsupported_action',
    },
  );
  const payload = trackEvent.mock.calls[0][1];
  for (const key of [
    'url',
    'credential',
    'client_secret',
    'paySign',
    'raw_error',
    'provider_payload',
    'token',
  ])
    expect(payload).not.toHaveProperty(key);
  rerender({ ...props });
  expect(trackEvent).toHaveBeenCalledTimes(1);
  rerender({ ...props, open: false });
  rerender(props);
  expect(trackEvent).toHaveBeenCalledTimes(2);
});

test.each([
  { open: false },
  { isLoggedIn: false },
  { previewMode: true },
  { shifuBid: '' },
  { orderId: '' },
  { reason: undefined },
])('excludes ineligible or non-actionable exposures %p', override => {
  renderHook(() =>
    usePaymentActionUnavailableTracking({ ...props, ...override }),
  );
  expect(trackEvent).not.toHaveBeenCalled();
});

test('a tracking failure remains independent of the recovery display', () => {
  trackEvent.mockImplementation(() => {
    throw new Error('offline');
  });
  expect(() =>
    renderHook(() => usePaymentActionUnavailableTracking(props)),
  ).not.toThrow();
});
