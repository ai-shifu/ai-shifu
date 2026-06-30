import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import MainMenuModal from './MainMenuModal';

const mockUpdateUserInfo = jest.fn();
const mockTrackEvent = jest.fn();
const mockRefreshUserInfo = jest.fn();
const mockRequestReplayAll = jest.fn();

const mockEnvState = {
  loginMethodsEnabled: ['password', 'phone'],
};

const mockUserStoreState = {
  isLoggedIn: true,
  userInfo: {
    mobile: '13800000000',
    email: 'user@example.com',
    is_creator: false,
  },
  logout: jest.fn(),
  refreshUserInfo: mockRefreshUserInfo,
  updateUserInfo: jest.fn(),
};

jest.mock('next/image', () => ({
  __esModule: true,
  default: ({ alt, src }: { alt: string; src: string }) =>
    React.createElement('img', { alt, src }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    language: 'en-US',
  },
  normalizeLanguage: (language: string) => language,
}));

jest.mock('@/lib/utils', () => ({
  cn: (...values: Array<string | false | null | undefined>) =>
    values.filter(Boolean).join(' '),
}));

jest.mock('@/c-store/envStore', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserStoreState) => unknown) =>
    selector(mockUserStoreState),
  useOnboardingReplayStore: (selector: (state: unknown) => unknown) =>
    selector({
      replayScenes: {
        admin_home_onboarding: false,
        course_editor_onboarding: false,
      },
      requestReplayAll: mockRequestReplayAll,
      clearReplay: jest.fn(),
    }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  EVENT_NAMES: {
    USER_MENU_BASIC_INFO: 'USER_MENU_BASIC_INFO',
    USER_MENU_PERSONALIZED: 'USER_MENU_PERSONALIZED',
    USER_MENU_SET_PASSWORD: 'USER_MENU_SET_PASSWORD',
    POP_LOGIN: 'POP_LOGIN',
  },
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
}));

jest.mock('@/c-service/Shifu', () => ({
  shifu: {
    loginTools: {
      openLogin: jest.fn(),
    },
  },
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    updateUserInfo: (...args: unknown[]) => mockUpdateUserInfo(...args),
  },
}));

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: {
    getState: () => ({
      updateLanguage: jest.fn(),
    }),
  },
}));

jest.mock('@/components/language-select', () => ({
  __esModule: true,
  default: () => <div>language-select</div>,
}));

jest.mock('@/c-components/PopupModal', () => ({
  __esModule: true,
  default: ({
    open,
    children,
  }: {
    open: boolean;
    children: React.ReactNode;
  }) => (open ? <div>{children}</div> : null),
}));

jest.mock('../Settings/SetPasswordModal', () => ({
  __esModule: true,
  SetPasswordModal: undefined,
  default: ({ open }: { open: boolean }) =>
    open ? (
      <div data-testid='set-password-modal'>set-password-modal</div>
    ) : null,
}));

jest.mock('@/components/ui/AlertDialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogAction: ({
    children,
    onClick,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
  }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => (
    <button>{children}</button>
  ),
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

describe('MainMenuModal', () => {
  beforeEach(() => {
    mockTrackEvent.mockReset();
    mockRefreshUserInfo.mockReset();
    mockUpdateUserInfo.mockReset();
    mockRequestReplayAll.mockReset();
    mockUserStoreState.isLoggedIn = true;
    mockUserStoreState.userInfo = {
      mobile: '13800000000',
      email: 'user@example.com',
      is_creator: false,
    };
    mockEnvState.loginMethodsEnabled = ['password', 'phone'];
  });

  test('shows set password entry in admin menu and opens the modal', () => {
    render(
      <MainMenuModal
        open
        onClose={jest.fn()}
        onBasicInfoClick={jest.fn()}
        onPersonalInfoClick={jest.fn()}
        isAdmin
      />,
    );

    expect(
      screen.queryByText('component.menus.navigationMenus.personalInfo'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('component.menus.navigationMenus.createCourse'),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('module.settings.setPassword'));

    expect(screen.getByTestId('set-password-modal')).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenCalledWith('USER_MENU_SET_PASSWORD', {});
  });

  test('replays onboarding from the admin menu and closes the modal', () => {
    const onClose = jest.fn();

    render(
      <MainMenuModal
        open
        onClose={onClose}
        onBasicInfoClick={jest.fn()}
        onPersonalInfoClick={jest.fn()}
        isAdmin
      />,
    );

    fireEvent.click(screen.getByText('module.onboarding.common.replay'));

    expect(mockRequestReplayAll).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('hides set password entry in admin menu when no password login or contact method is available', () => {
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockUserStoreState.userInfo = {
      mobile: '',
      email: '',
      is_creator: false,
    };

    render(
      <MainMenuModal
        open
        onClose={jest.fn()}
        onBasicInfoClick={jest.fn()}
        onPersonalInfoClick={jest.fn()}
        isAdmin
      />,
    );

    expect(
      screen.queryByText('module.settings.setPassword'),
    ).not.toBeInTheDocument();
  });

  test('hides set password entry when contact methods only contain whitespace', () => {
    mockUserStoreState.userInfo = {
      mobile: '   ',
      email: '\t',
      is_creator: false,
    };

    render(
      <MainMenuModal
        open
        onClose={jest.fn()}
        onBasicInfoClick={jest.fn()}
        onPersonalInfoClick={jest.fn()}
        isAdmin
      />,
    );

    expect(
      screen.queryByText('module.settings.setPassword'),
    ).not.toBeInTheDocument();
  });
});
