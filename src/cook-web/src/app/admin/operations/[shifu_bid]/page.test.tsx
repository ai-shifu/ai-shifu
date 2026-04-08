import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AdminOperationCourseDetailPage from './page';

const mockReplace = jest.fn();
const mockPush = jest.fn();

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
    push: mockPush,
  }),
  useParams: () => ({
    shifu_bid: 'course-1',
  }),
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserState) => unknown) =>
    selector(mockUserState),
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => {
    const ns = Array.isArray(namespace) ? namespace[0] : namespace;
    return {
      t: (key: string) => (ns && ns !== 'translation' ? `${ns}.${key}` : key),
    };
  },
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

describe('AdminOperationCourseDetailPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = {
      is_operator: true,
    };
  });

  test('renders placeholder detail page and can go back', async () => {
    render(<AdminOperationCourseDetailPage />);

    expect(
      await screen.findByText('module.operationsCourse.detail.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('course-1')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.back',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith('/admin/operations');
  });

  test('redirects non-operators back to admin', async () => {
    mockUserState.userInfo = {
      is_operator: false,
    };

    render(<AdminOperationCourseDetailPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
  });
});
