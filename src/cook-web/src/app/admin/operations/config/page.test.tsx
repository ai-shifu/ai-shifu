import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import AdminOperationsConfigPage from './page';

const mockToast = jest.fn();
const mockT = (key: string) =>
  new Map([
    ['title', '费率管理'],
    ['actions.addConfiguration', '添加费率'],
  ]).get(key) || key;

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationConfigRates: jest.fn(),
    updateAdminOperationConfigRate: jest.fn(),
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: mockT }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('../useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({ isReady: true }),
}));

jest.mock('@/app/admin/components/AdminBreadcrumb', () => ({
  __esModule: true,
  default: () => <div data-testid='breadcrumb' />,
}));

jest.mock('@/app/admin/components/AdminTitle', () => ({
  __esModule: true,
  default: ({
    title,
    actions,
    tabs,
  }: {
    title: React.ReactNode;
    actions: React.ReactNode;
    tabs: React.ReactNode;
  }) => (
    <section>
      <h1>{title}</h1>
      {actions}
      {tabs}
    </section>
  ),
}));

jest.mock('@/components/admin/AdminTableShell', () => ({
  __esModule: true,
  default: () => <div data-testid='rate-table' />,
}));

jest.mock('@/components/ui/Tabs', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const TabsContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({ value: '', onValueChange: () => undefined });

  return {
    Tabs: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange: (value: string) => void;
    }>) => (
      <TabsContext.Provider value={{ value, onValueChange }}>
        {children}
      </TabsContext.Provider>
    ),
    TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
    TabsTrigger: ({
      value,
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(TabsContext);
      return (
        <button
          type='button'
          onClick={() => context.onValueChange(value)}
        >
          {children}
        </button>
      );
    },
    TabsContent: ({
      value,
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(TabsContext);
      return context.value === value ? <div>{children}</div> : null;
    },
  };
});

jest.mock('./RateCreateDialog', () => ({
  __esModule: true,
  default: ({
    open,
    usageType,
    onCreate,
  }: {
    open: boolean;
    usageType: string;
    onCreate: (
      payload: Record<string, unknown>,
      identity: Record<string, unknown>,
    ) => Promise<boolean>;
  }) =>
    open ? (
      <div data-testid='create-rate-dialog'>
        <span data-testid='create-rate-usage-type'>{usageType}</span>
        <button
          type='button'
          aria-label='mock-create'
          onClick={() =>
            void onCreate(
              {
                create_only: true,
                usage_type: 'tts',
                provider: 'tencent',
                model: '',
                rate_model: '',
                billing_metric: 'tts_output_chars',
                unit_size: 1,
                credits_per_unit: 1,
                status: 'active',
              },
              {
                usageType: 'tts',
                provider: 'tencent',
                model: '',
                rateModel: '',
              },
            )
          }
        />
      </div>
    ) : null,
}));

const mockGetRates = api.getAdminOperationConfigRates as jest.Mock;
const mockUpdateRate = api.updateAdminOperationConfigRate as jest.Mock;

describe('AdminOperationsConfigPage create-rate wiring', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetRates.mockResolvedValue({
      baseline: {
        is_configured: true,
        unit_cost: 0.25,
        tts_chars_per_llm_token: 0.5,
      },
      llm_rates: [],
      tts_rates: [],
    });
    mockUpdateRate.mockResolvedValue({});
  });

  test('opens the CTA for the current tab, posts create-only data, and reloads rates', async () => {
    render(<AdminOperationsConfigPage />);

    expect(
      screen.getByRole('heading', { name: '费率管理' }),
    ).toBeInTheDocument();
    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: 'tabs.tts' }));
    fireEvent.click(screen.getByRole('button', { name: '添加费率' }));

    expect(screen.getByTestId('create-rate-usage-type')).toHaveTextContent(
      'tts',
    );
    fireEvent.click(screen.getByRole('button', { name: 'mock-create' }));

    await waitFor(() =>
      expect(mockUpdateRate).toHaveBeenCalledWith({
        create_only: true,
        usage_type: 'tts',
        provider: 'tencent',
        model: '',
        rate_model: '',
        billing_metric: 'tts_output_chars',
        unit_size: 1,
        credits_per_unit: 1,
        status: 'active',
      }),
    );
    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(2));
    expect(mockToast).toHaveBeenCalledWith({ title: 'create.success' });
  });
});
