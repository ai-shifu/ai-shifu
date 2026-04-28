import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AdminOperationOrdersPage from './page';

let mockSearchParamsValue = '';
const mockReplace = jest.fn();
const LEARN_TAB_CONTENT = 'learn-orders-tab';
const CREDIT_TAB_CONTENT = 'credit-orders-tab';

jest.mock('next/navigation', () => ({
  usePathname: () => '/admin/operations/orders',
  useRouter: () => ({
    replace: mockReplace,
  }),
  useSearchParams: () => new URLSearchParams(mockSearchParamsValue),
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => ({
    t: (key: string) => {
      const ns = Array.isArray(namespace) ? namespace[0] : namespace;
      return ns ? `${ns}.${key}` : key;
    },
  }),
}));

jest.mock('../useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({
    isReady: true,
  }),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ui/Tabs', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const TabsContext = ReactModule.createContext<{
    value: string;
    onValueChange?: (value: string) => void;
  }>({
    value: '',
  });

  return {
    __esModule: true,
    Tabs: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange?: (value: string) => void;
    }>) => (
      <TabsContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
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
          role='tab'
          type='button'
          aria-selected={context.value === value}
          onClick={() => context.onValueChange?.(value)}
        >
          {children}
        </button>
      );
    },
  };
});

jest.mock('./LearnOrdersTab', () => ({
  __esModule: true,
  default: () => {
    const label = 'learn-orders-tab';
    return <div>{label}</div>;
  },
}));

jest.mock('./CreditOrdersTab', () => ({
  __esModule: true,
  default: () => {
    const label = 'credit-orders-tab';
    return <div>{label}</div>;
  },
}));

describe('AdminOperationOrdersPage', () => {
  beforeEach(() => {
    mockSearchParamsValue = '';
    mockReplace.mockReset();
  });

  test('defaults to learn tab without tab query', () => {
    render(<AdminOperationOrdersPage />);

    expect(screen.getByText(LEARN_TAB_CONTENT)).toBeInTheDocument();
    expect(screen.queryByText(CREDIT_TAB_CONTENT)).not.toBeInTheDocument();
  });

  test('renders credits tab from query and updates url when switching', () => {
    mockSearchParamsValue = 'tab=credits';

    render(<AdminOperationOrdersPage />);

    expect(screen.getByText(CREDIT_TAB_CONTENT)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('tab', {
        name: 'module.operationsOrder.tabs.learn',
      }),
    );

    expect(mockReplace).toHaveBeenCalledWith('/admin/operations/orders', {
      scroll: false,
    });
  });
});
