import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Page from './page';
let mockReady = true;
const mockReplace = jest.fn();
const mockTrack = jest.fn();
const mockPanel = jest.fn();
const mockMutate = jest.fn();
const mockCatalogProvider = (provider: string) => ({
  provider,
  label_key: provider,
  catalog: true,
  discounts: true,
});
let mockMetadata = {
  data: { items: [mockCatalogProvider('fixture-catalog')] },
  isLoading: false,
  error: undefined as Error | undefined,
  mutate: mockMutate,
};
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace }),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock('@/store', () => ({
  useEnvStore: (selector: any) =>
    selector({ billingEnabled: 'true', runtimeConfigLoaded: true }),
}));
jest.mock('@/app/admin/operations/useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({ isReady: mockReady }),
}));
jest.mock('@/hooks/useBillingPaymentProviders', () => ({
  useBillingPaymentProviders: () => mockMetadata,
}));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrack }),
}));
jest.mock('@/app/admin/components/AdminBreadcrumb', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('@/app/admin/components/AdminTitle', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div>loading</div>,
}));
jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ onRetry }: any) => <button onClick={onRetry}>retry</button>,
}));
jest.mock('./AdminBillingProviderPricesPanel', () => ({
  AdminBillingProviderPricesPanel: (props: any) => {
    mockPanel(props);
    return <div>{props.provider}</div>;
  },
}));
beforeEach(() => {
  mockReady = true;
  jest.clearAllMocks();
  mockTrack.mockReset().mockResolvedValue(undefined);
  mockMetadata = {
    data: { items: [mockCatalogProvider('fixture-catalog')] },
    isLoading: false,
    error: undefined,
    mutate: mockMutate,
  };
});
test.each(['fixture-catalog', 'stripe'])(
  'opens a capable provider without a Stripe-specific page gate: %s',
  provider => {
    mockMetadata.data.items = [mockCatalogProvider(provider)];
    render(<Page />);
    expect(mockPanel).toHaveBeenCalledWith({
      provider,
      providerLabel: provider,
    });
    expect(mockReplace).not.toHaveBeenCalled();
    expect(mockTrack).not.toHaveBeenCalled();
  },
);
test.each(['reject', 'throw', 'success'])(
  'selection reaches panel and survives tracking %s',
  async failure => {
    mockMetadata.data.items = [
      mockCatalogProvider('stripe'),
      mockCatalogProvider('fixture-catalog'),
    ];
    if (failure === 'reject')
      mockTrack.mockRejectedValue(new Error('analytics unavailable'));
    if (failure === 'throw')
      mockTrack.mockImplementation(() => {
        throw new Error('analytics unavailable');
      });
    const view = render(<Page />);
    expect(mockTrack).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('combobox'), {
      target: { value: 'fixture-catalog' },
    });
    expect(mockPanel).toHaveBeenLastCalledWith({
      provider: 'fixture-catalog',
      providerLabel: 'fixture-catalog',
    });
    expect(mockTrack).toHaveBeenCalledTimes(1);
    expect(mockTrack).toHaveBeenCalledWith('admin_payment_provider_selected', {
      surface: 'prices',
    });
    view.rerender(<Page />);
    expect(mockTrack).toHaveBeenCalledTimes(1);
    await Promise.resolve();
  },
);
test('waits for discovery instead of redirecting while capabilities load', () => {
  mockMetadata.data.items = [];
  mockMetadata.isLoading = true;
  render(<Page />);
  expect(mockReplace).not.toHaveBeenCalled();
});
test('redirects only after discovery confirms no catalog provider', async () => {
  mockMetadata.data.items = [];
  render(<Page />);
  await waitFor(() =>
    expect(mockReplace).toHaveBeenCalledWith('/admin/operations'),
  );
});
test('discovery failure offers retry without pretending there are no providers', () => {
  mockMetadata.error = new Error('unavailable');
  render(<Page />);
  fireEvent.click(screen.getByRole('button', { name: 'retry' }));
  expect(mockMutate).toHaveBeenCalledTimes(1);
  expect(mockReplace).not.toHaveBeenCalled();
});

test('unchanged selection and non-operator rendering emit no analytics', () => {
  mockMetadata.data.items = [
    mockCatalogProvider('stripe'),
    mockCatalogProvider('fixture-catalog'),
  ];
  const view = render(<Page />);
  fireEvent.change(screen.getByRole('combobox'), {
    target: { value: 'stripe' },
  });
  expect(mockTrack).not.toHaveBeenCalled();
  mockPanel.mockClear();
  mockReady = false;
  view.rerender(<Page />);
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  expect(mockPanel).not.toHaveBeenCalled();
  expect(mockTrack).not.toHaveBeenCalled();
  expect(mockReplace).not.toHaveBeenCalled();
});
