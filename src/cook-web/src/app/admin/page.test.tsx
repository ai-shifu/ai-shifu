import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';

import AdminPage from './page';

const mockPush = jest.fn();
const mockT = (key: string) => key;
const mockI18n = {
  language: 'en-US',
};
const CLOSE_IMPORT_LABEL = 'close-import';
const CLOSE_REDEMPTION_LABEL = 'close-redemption';

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

jest.mock('next/link', () => {
  function MockLink({
    children,
    href,
  }: React.PropsWithChildren<{ href: string }>) {
    return <a href={href}>{children}</a>;
  }

  MockLink.displayName = 'MockLink';

  return MockLink;
});

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    ensureAdminCreator: jest.fn(),
    getShifuList: jest.fn(),
    createShifu: jest.fn(),
    archiveShifu: jest.fn(),
    unarchiveShifu: jest.fn(),
  },
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (
    selector: (state: {
      isInitialized: boolean;
      isGuest: boolean;
      isLoggedIn: boolean;
      userInfo: { user_id: string };
    }) => unknown,
  ) =>
    selector({
      isInitialized: true,
      isGuest: false,
      isLoggedIn: true,
      userInfo: { user_id: 'user-1' },
    }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: jest.fn(),
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: jest.fn(),
  }),
}));

jest.mock('@/hooks/useOnboarding', () => ({
  useCreatorOnboardingStatus: () => ({
    data: null,
  }),
}));

jest.mock('@/c-utils/urlUtils', () => ({
  getCourseCreatorUrl: () => null,
}));

jest.mock('@/lib/onboardingTargets', () => ({
  buildGuideCourseTargetId: () => undefined,
  buildOnboardingTargetProps: () => ({}),
  ONBOARDING_TARGET_IDS: {
    courseCreationEntry: 'courseCreationEntry',
    lobsterCreateEntry: 'lobsterCreateEntry',
    blankCreateEntry: 'blankCreateEntry',
  },
}));

jest.mock('@/lib/shifu-permissions', () => ({
  canManageArchive: () => true,
  canManageOwnerCourseAction: (
    shifu: { created_user_bid?: string } | null | undefined,
    currentUserId: string,
  ) => shifu?.created_user_bid === currentUserId,
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockT,
    i18n: mockI18n,
  }),
}));

jest.mock('@/components/ui/Tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({
    children,
    value,
  }: React.PropsWithChildren<{ value: string }>) => (
    <button type='button'>{children || value}</button>
  ),
}));

jest.mock('@/components/ui/Button', () => ({
  Button: ({
    children,
    onClick,
    ...props
  }: React.PropsWithChildren<{
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
  }>) => (
    <button
      type='button'
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/Card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/components/ui/Badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}));

jest.mock('@/components/ui/DropdownMenu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuItem: ({
    children,
    onSelect,
  }: React.PropsWithChildren<{
    onSelect?: (event: { stopPropagation: () => void }) => void;
  }>) => (
    <button
      type='button'
      onClick={() => onSelect?.({ stopPropagation: () => undefined })}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/AlertDialog', () => ({
  AlertDialog: ({
    open,
    children,
  }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  AlertDialogAction: ({
    children,
    onClick,
  }: React.PropsWithChildren<{
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
  }>) => (
    <button
      type='button'
      onClick={onClick}
    >
      {children}
    </button>
  ),
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => (
    <button type='button'>{children}</button>
  ),
  AlertDialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/create-shifu-dialog', () => ({
  CreateShifuDialog: () => null,
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage: string }) => (
    <div>{errorMessage}</div>
  ),
}));

jest.mock('@/components/MobileUnsupportedDialog', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/components/shifu-setting/ShifuPermissionDialog', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('./components/AdminBreadcrumb', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('./components/AdminTitle', () => ({
  __esModule: true,
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));

jest.mock('@/components/order/ImportActivationDialog', () => ({
  __esModule: true,
  default: ({
    open,
    initialCourseId,
    initialCourseName,
    onOpenChange,
  }: {
    open: boolean;
    initialCourseId?: string;
    initialCourseName?: string;
    onOpenChange: (open: boolean) => void;
  }) => (
    <div
      data-testid='import-activation-dialog'
      data-open={String(open)}
    >
      <div data-testid='import-course-id'>{initialCourseId || 'none'}</div>
      <div data-testid='import-course-name'>{initialCourseName || 'none'}</div>
      <button
        type='button'
        onClick={() => onOpenChange(false)}
      >
        {CLOSE_IMPORT_LABEL}
      </button>
    </div>
  ),
}));

jest.mock('./orders/CreatorRedemptionCodeDialog', () => ({
  __esModule: true,
  default: ({
    open,
    initialShifuBid,
    initialShifuName,
    onOpenChange,
  }: {
    open: boolean;
    initialShifuBid?: string;
    initialShifuName?: string;
    onOpenChange: (open: boolean) => void;
  }) => (
    <div
      data-testid='creator-redemption-dialog'
      data-open={String(open)}
    >
      <div data-testid='redemption-shifu-id'>{initialShifuBid || 'none'}</div>
      <div data-testid='redemption-shifu-name'>
        {initialShifuName || 'none'}
      </div>
      <button
        type='button'
        onClick={() => onOpenChange(false)}
      >
        {CLOSE_REDEMPTION_LABEL}
      </button>
    </div>
  ),
}));

const mockEnsureAdminCreator = api.ensureAdminCreator as jest.Mock;
const mockGetShifuList = api.getShifuList as jest.Mock;

describe('AdminPage', () => {
  let consoleInfoSpy: jest.SpyInstance;

  beforeEach(() => {
    mockPush.mockReset();
    mockEnsureAdminCreator.mockReset();
    mockGetShifuList.mockReset();
    consoleInfoSpy = jest
      .spyOn(console, 'info')
      .mockImplementation(() => undefined);
    mockEnsureAdminCreator.mockResolvedValue({});
    mockGetShifuList.mockResolvedValue({
      items: [
        {
          bid: 'course-1',
          name: 'Course 1',
          description: 'Course description',
          archived: false,
          avatar: '',
          is_favorite: false,
          created_user_bid: 'user-1',
          can_manage_permissions: true,
        },
      ],
    });

    class MockIntersectionObserver {
      observe() {}
      disconnect() {}
      unobserve() {}
    }

    global.IntersectionObserver =
      MockIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  afterEach(() => {
    consoleInfoSpy.mockRestore();
  });

  test('opens redemption dialog from the course card menu and keeps the course locked until close animation finishes', async () => {
    render(<AdminPage />);

    await waitFor(() => {
      expect(mockEnsureAdminCreator).toHaveBeenCalledWith({});
      expect(mockGetShifuList).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 30,
        archived: false,
      });
      expect(screen.getByText('Course 1')).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.more',
      }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.redemptionCodes.action',
      }),
    );

    expect(screen.getByTestId('creator-redemption-dialog')).toHaveAttribute(
      'data-open',
      'true',
    );
    expect(screen.getByTestId('redemption-shifu-id')).toHaveTextContent(
      'course-1',
    );
    expect(screen.getByTestId('redemption-shifu-name')).toHaveTextContent(
      'Course 1',
    );

    fireEvent.click(
      screen.getByRole('button', { name: CLOSE_REDEMPTION_LABEL }),
    );

    expect(screen.getByTestId('creator-redemption-dialog')).toHaveAttribute(
      'data-open',
      'false',
    );
    expect(screen.getByTestId('redemption-shifu-id')).toHaveTextContent(
      'course-1',
    );

    await waitFor(
      () => {
        expect(screen.getByTestId('redemption-shifu-id')).toHaveTextContent(
          'none',
        );
      },
      { timeout: 500 },
    );
  });

  test('does not show owner-only course actions for shared-permission courses', async () => {
    mockGetShifuList.mockResolvedValue({
      items: [
        {
          bid: 'course-shared-1',
          name: 'Shared Course',
          description: 'Shared course description',
          archived: false,
          avatar: '',
          is_favorite: false,
          created_user_bid: 'owner-1',
          can_manage_permissions: false,
        },
      ],
    });

    render(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByText('Shared Course')).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.more',
      }),
    );

    expect(
      screen.queryByRole('button', {
        name: 'module.order.importActivation.action',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.order.redemptionCodes.action',
      }),
    ).not.toBeInTheDocument();
  });
});
