import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import api from '@/api';
import { useBillingPaymentProviders } from './useBillingPaymentProviders';
jest.mock('@/api', () => ({
  __esModule: true,
  default: { getAdminBillingPaymentProviders: jest.fn() },
}));
const mockGet = api.getAdminBillingPaymentProviders as jest.Mock;
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false }}>
    {children}
  </SWRConfig>
);
beforeEach(() => mockGet.mockReset());
test('uses the protected shared API and preserves arbitrary capability declarations', async () => {
  const data = {
    items: [
      {
        provider: 'fixture-catalog',
        label_key: 'fixture.catalog',
        catalog: true,
        discounts: true,
      },
    ],
    discount_sync_required: true,
  };
  mockGet.mockResolvedValue(data);
  const { result } = renderHook(() => useBillingPaymentProviders(true), {
    wrapper,
  });
  await waitFor(() => expect(result.current.data).toEqual(data));
  expect(mockGet).toHaveBeenCalledWith({}, { skipErrorToast: true });
});
test('non-operators and disabled billing do not request protected discovery', () => {
  renderHook(() => useBillingPaymentProviders(false), { wrapper });
  expect(mockGet).not.toHaveBeenCalled();
});
test('retains a discovery failure for visible retry handling', async () => {
  const error = new Error('unavailable');
  mockGet.mockRejectedValue(error);
  const { result } = renderHook(() => useBillingPaymentProviders(true), {
    wrapper,
  });
  await waitFor(() => expect(result.current.error).toBe(error));
  expect(result.current.data).toBeUndefined();
});
