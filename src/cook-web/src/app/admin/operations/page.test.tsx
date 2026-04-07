import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import AdminOperationsPage from './page';

const mockReplace = jest.fn();
const mockTranslate = (key: string) => key;

const mockUserState = {
  isInitialized: true,
  isGuest: false,
  userInfo: {
    is_operator: true,
  },
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserState) => unknown) =>
    selector(mockUserState),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockTranslate,
  }),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

describe('AdminOperationsPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = {
      is_operator: true,
    };
  });

  test('renders operations page for operators', () => {
    render(<AdminOperationsPage />);

    expect(screen.getByText('common.core.operations')).toBeInTheDocument();
    expect(
      screen.getByText('common.core.waitingForCompletion'),
    ).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  test('redirects non-operators back to admin', async () => {
    mockUserState.userInfo = {
      is_operator: false,
    };

    render(<AdminOperationsPage />);

    expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
  });

  test('redirects to admin when user info is unexpectedly missing', async () => {
    mockUserState.userInfo = null as any;

    render(<AdminOperationsPage />);

    expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
  });
});
