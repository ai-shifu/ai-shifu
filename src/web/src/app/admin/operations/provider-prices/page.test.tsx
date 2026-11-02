import React from 'react';
import { render, screen } from '@testing-library/react';
import type { RuntimeConfigContext } from '@/types/store';
import AdminOperationProviderPricesPage from './page';

const mockReplace = jest.fn();
const mockEnvState = {
  billingEnabled: 'true',
  stripeEnabled: 'true',
  paymentChannels: ['stripe'],
  runtimeConfigLoaded: true,
  runtimeConfigContext: {
    courseId: '',
    status: 'ready',
    generation: 1,
  } as RuntimeConfigContext | null,
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/store', () => ({
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('../use-operator-guard', () => ({
  __esModule: true,
  default: () => ({ isReady: true }),
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
  default: () => <div data-testid='loading' />,
}));

jest.mock('./AdminBillingProviderPricesPanel', () => ({
  AdminBillingProviderPricesPanel: () => (
    <div data-testid='provider-prices-panel' />
  ),
}));

describe('AdminOperationProviderPricesPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockEnvState.billingEnabled = 'true';
    mockEnvState.stripeEnabled = 'true';
    mockEnvState.paymentChannels = ['stripe'];
    mockEnvState.runtimeConfigLoaded = true;
    mockEnvState.runtimeConfigContext = {
      courseId: '',
      status: 'ready',
      generation: 1,
    };
  });

  test.each<{
    name: string;
    context: RuntimeConfigContext | null;
    loaded?: boolean;
  }>([
    {
      name: 'unfinished global bootstrap',
      context: { courseId: '', status: 'ready', generation: 2 },
      loaded: false,
    },
    { name: 'unknown context', context: null },
    {
      name: 'loading admin context',
      context: { courseId: '', status: 'loading', generation: 2 },
    },
    {
      name: 'loading course context',
      context: { courseId: 'course-a', status: 'loading', generation: 2 },
    },
    {
      name: 'ready course context',
      context: { courseId: 'course-a', status: 'ready', generation: 2 },
    },
    {
      name: 'failed course context',
      context: { courseId: 'course-a', status: 'failed', generation: 2 },
    },
  ])('waits for admin runtime config during $name', ({ context, loaded }) => {
    mockEnvState.runtimeConfigContext = context;
    mockEnvState.runtimeConfigLoaded = loaded ?? true;

    const { rerender } = render(<AdminOperationProviderPricesPage />);

    expect(screen.getByTestId('loading')).toBeInTheDocument();
    expect(
      screen.queryByTestId('provider-prices-panel'),
    ).not.toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();

    mockEnvState.billingEnabled = 'false';
    mockEnvState.stripeEnabled = 'false';
    mockEnvState.paymentChannels = [];
    rerender(<AdminOperationProviderPricesPage />);

    expect(mockReplace).not.toHaveBeenCalled();

    mockEnvState.runtimeConfigLoaded = true;
    mockEnvState.runtimeConfigContext = {
      courseId: '',
      status: 'ready',
      generation: 3,
    };
    rerender(<AdminOperationProviderPricesPage />);

    expect(mockReplace).toHaveBeenCalledWith('/admin/operations');
  });

  test.each(['ready', 'failed'] as const)(
    'redirects when Stripe billing is disabled after admin config is %s',
    status => {
      mockEnvState.billingEnabled = 'false';
      mockEnvState.stripeEnabled = 'false';
      mockEnvState.paymentChannels = [];
      mockEnvState.runtimeConfigContext = {
        courseId: '',
        status,
        generation: 2,
      };

      render(<AdminOperationProviderPricesPage />);

      expect(mockReplace).toHaveBeenCalledWith('/admin/operations');
      expect(
        screen.queryByTestId('provider-prices-panel'),
      ).not.toBeInTheDocument();
    },
  );

  test('renders enabled Stripe billing after admin config is ready', () => {
    render(<AdminOperationProviderPricesPage />);

    expect(screen.getByTestId('provider-prices-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('loading')).not.toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
