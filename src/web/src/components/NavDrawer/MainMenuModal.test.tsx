import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import MainMenuModal from './MainMenuModal';
import arabicMenus from '../../../../i18n/ar-SA/components/menus.json';
import germanMenus from '../../../../i18n/de-DE/components/menus.json';
import englishMenus from '../../../../i18n/en-US/components/menus.json';
import spanishMenus from '../../../../i18n/es-ES/components/menus.json';
import frenchMenus from '../../../../i18n/fr-FR/components/menus.json';
import thaiMenus from '../../../../i18n/th-TH/components/menus.json';
import urduMenus from '../../../../i18n/ur-PK/components/menus.json';
import chineseMenus from '../../../../i18n/zh-CN/components/menus.json';

const mockUpdateUserInfo = jest.fn();
const mockTrackEvent = jest.fn();
const mockRefreshUserInfo = jest.fn();
const mockEnvironment = {
  appVersion: '2.3.3',
  appBuildSha: 'a1b2c3d4e5f678901234567890123456789012345',
};
let mockVersionLabel = 'Version';

const mockEnvState = {
  loginMethodsEnabled: ['password', 'phone'],
};
const mockSystemState = { previewMode: false };

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
    t: (key: string) =>
      key === 'component.menus.navigationMenus.version'
        ? mockVersionLabel
        : key,
  }),
}));

jest.mock('@/config/environment', () => ({
  get environment() {
    return mockEnvironment;
  },
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

jest.mock('@/store/envStore', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserStoreState) => unknown) =>
    selector(mockUserStoreState),
}));

jest.mock('@/hooks/useTracking', () => ({
  EVENT_NAMES: {
    USER_MENU_BASIC_INFO: 'USER_MENU_BASIC_INFO',
    USER_MENU_PERSONALIZED: 'USER_MENU_PERSONALIZED',
    USER_MENU_SET_PASSWORD: 'USER_MENU_SET_PASSWORD',
    USER_APP_VERSION_VIEWED:
      jest.requireActual('@/lib/tracking').EVENT_NAMES.USER_APP_VERSION_VIEWED,
    POP_LOGIN: 'POP_LOGIN',
  },
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
}));

jest.mock('@/lib/shifu/Shifu', () => ({
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

jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: Object.assign(
    (selector: (state: typeof mockSystemState) => unknown) =>
      selector(mockSystemState),
    {
      getState: () => ({
        updateLanguage: jest.fn(),
      }),
    },
  ),
}));

jest.mock('../Settings/CourseMemoryDialog', () => ({
  __esModule: true,
  default: ({ courseId }: { courseId: string }) => (
    <div data-testid='course-memory'>{courseId}</div>
  ),
}));

jest.mock('@/components/language-select', () => ({
  __esModule: true,
  default: ({ analyticsSurface }: { analyticsSurface: string }) => (
    <div
      data-testid='language-select'
      data-analytics-surface={analyticsSurface}
    >
      language-select
    </div>
  ),
}));

jest.mock('@/components/PopupModal', () => ({
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
    mockUserStoreState.isLoggedIn = true;
    mockUserStoreState.userInfo = {
      mobile: '13800000000',
      email: 'user@example.com',
      is_creator: false,
    };
    mockEnvState.loginMethodsEnabled = ['password', 'phone'];
    mockSystemState.previewMode = false;
    mockEnvironment.appVersion = '2.3.3';
    mockEnvironment.appBuildSha = 'a1b2c3d4e5f678901234567890123456789012345';
    mockVersionLabel = 'Version';
  });

  test.each([
    ['admin', false, false],
    ['admin', true, true],
    ['learner', false, true],
    ['learner', true, false],
  ] as const)(
    'shows and tracks the committed version for surface=%s member=%s mobile=%s',
    (surface, member, mobileStyle) => {
      mockUserStoreState.isLoggedIn = member;
      let versionPresentAtEmission = false;
      mockTrackEvent.mockImplementation(() => {
        versionPresentAtEmission = !!screen.queryByText('v2.3.3 · a1b2c3d');
      });
      render(
        <MainMenuModal
          open
          surface={surface}
          mobileStyle={mobileStyle}
          onPersonalInfoClick={jest.fn()}
        />,
      );

      const build = screen.getByText('v2.3.3 · a1b2c3d');
      const version = build.parentElement;
      expect(version).toHaveTextContent('Version v2.3.3 · a1b2c3d');
      expect(build).toHaveAttribute('dir', 'ltr');
      expect(version?.tagName).toBe('DIV');
      expect(version).not.toHaveAttribute('role');
      expect(version).not.toHaveAttribute('tabindex');
      expect(version?.previousElementSibling).toHaveTextContent(
        member ? 'module.user.logout' : 'module.user.login',
      );
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      expect(versionPresentAtEmission).toBe(true);
      expect(mockTrackEvent).toHaveBeenCalledWith('user_app_version_viewed', {
        surface,
      });
      expect(Object.keys(mockTrackEvent.mock.calls[0][1])).toEqual(['surface']);
    },
  );

  test.each([
    ['ar-SA', arabicMenus],
    ['de-DE', germanMenus],
    ['en-US', englishMenus],
    ['es-ES', spanishMenus],
    ['fr-FR', frenchMenus],
    ['th-TH', thaiMenus],
    ['ur-PK', urduMenus],
    ['zh-CN', chineseMenus],
  ] as const)(
    'renders the localized version label for %s',
    (_locale, menus) => {
      mockVersionLabel = menus.navigationMenus.version;
      render(
        <MainMenuModal
          open
          surface='learner'
          onPersonalInfoClick={jest.fn()}
        />,
      );
      expect(
        screen.getByText('v2.3.3 · a1b2c3d').parentElement,
      ).toHaveTextContent(`${menus.navigationMenus.version} v2.3.3 · a1b2c3d`);
    },
  );

  test('shows only the release version when the build SHA is unavailable', () => {
    mockEnvironment.appBuildSha = '';
    render(
      <MainMenuModal
        open
        surface='admin'
        onPersonalInfoClick={jest.fn()}
      />,
    );
    expect(screen.getByText('v2.3.3').parentElement).toHaveTextContent(
      /^Version v2\.3\.3$/,
    );
    expect(mockTrackEvent).toHaveBeenCalledWith('user_app_version_viewed', {
      surface: 'admin',
    });
  });

  test('does not render or track an unavailable release version', () => {
    mockEnvironment.appVersion = '';
    render(
      <MainMenuModal
        open
        surface='admin'
        onPersonalInfoClick={jest.fn()}
      />,
    );
    expect(screen.queryByText('Version')).not.toBeInTheDocument();
    expect(screen.queryByText(/a1b2c3d/)).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  test('tracks once per open, never for closed or repeated renders', () => {
    const props = {
      surface: 'learner' as const,
      onPersonalInfoClick: jest.fn(),
    };
    const { rerender } = render(
      <MainMenuModal
        {...props}
        open={false}
      />,
    );
    expect(screen.queryByText('v2.3.3 · a1b2c3d')).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalled();

    rerender(
      <MainMenuModal
        {...props}
        open
      />,
    );
    rerender(
      <MainMenuModal
        {...props}
        open
        mobileStyle
      />,
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);

    rerender(
      <MainMenuModal
        {...props}
        open={false}
      />,
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    rerender(
      <MainMenuModal
        {...props}
        open
      />,
    );
    expect(mockTrackEvent.mock.calls).toEqual([
      ['user_app_version_viewed', { surface: 'learner' }],
      ['user_app_version_viewed', { surface: 'learner' }],
    ]);
  });

  test('does not count Strict Mode effect replay as another menu open', () => {
    render(
      <React.StrictMode>
        <MainMenuModal
          open
          surface='admin'
          onPersonalInfoClick={jest.fn()}
        />
      </React.StrictMode>,
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  });

  test.each(['learner', 'admin'] as const)(
    'excludes learner preview only from version tracking on %s',
    surface => {
      mockSystemState.previewMode = true;
      render(
        <MainMenuModal
          open
          surface={surface}
          onPersonalInfoClick={jest.fn()}
        />,
      );
      expect(screen.getByText('v2.3.3 · a1b2c3d')).toBeInTheDocument();
      expect(mockTrackEvent).toHaveBeenCalledTimes(surface === 'admin' ? 1 : 0);
    },
  );

  test.each(['throws', 'rejects'])(
    'keeps the version visible when analytics %s',
    async failure => {
      if (failure === 'throws') {
        mockTrackEvent.mockImplementationOnce(() => {
          throw new Error('Analytics unavailable');
        });
      } else {
        mockTrackEvent.mockRejectedValueOnce(
          new Error('Analytics unavailable'),
        );
      }

      await act(async () => {
        render(
          <MainMenuModal
            open
            surface='admin'
            onPersonalInfoClick={jest.fn()}
          />,
        );
      });
      expect(screen.getByText('v2.3.3 · a1b2c3d')).toBeInTheDocument();
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      fireEvent.click(
        screen.getByRole('button', { name: 'module.settings.setPassword' }),
      );
      expect(screen.getByTestId('set-password-modal')).toBeInTheDocument();
    },
  );

  test.each([true, false])(
    'opens course memory for member=%s with one dialog on double click',
    member => {
      mockUserStoreState.isLoggedIn = member;
      const close = jest.fn();
      render(
        <MainMenuModal
          open
          surface='learner'
          courseId='course-id'
          onClose={close}
          onPersonalInfoClick={jest.fn()}
        />,
      );
      const entry = screen.getByRole('button', {
        name: 'module.settings.memoryTitle',
      });
      fireEvent.click(entry);
      fireEvent.click(entry);
      expect(screen.getAllByTestId('course-memory')).toHaveLength(1);
      expect(close).toHaveBeenCalledTimes(1);
    },
  );

  test.each(['admin', 'preview', 'no-course'])(
    'excludes %s from memory management',
    excluded => {
      mockSystemState.previewMode = excluded === 'preview';
      render(
        <MainMenuModal
          open
          surface={excluded === 'admin' ? 'admin' : 'learner'}
          courseId={excluded === 'no-course' ? undefined : 'course-id'}
          onPersonalInfoClick={jest.fn()}
        />,
      );
      expect(
        screen.queryByRole('button', { name: 'module.settings.memoryTitle' }),
      ).not.toBeInTheDocument();
      expect(screen.queryByTestId('course-memory')).not.toBeInTheDocument();
    },
  );

  test.each([
    {
      scenario: 'non-teacher learner',
      surface: 'learner' as const,
      isCreator: false,
      sceneLabel: 'component.menus.navigationMenus.createCourse',
      excludedSceneLabels: [
        'component.menus.navigationMenus.adminConsole',
        'component.menus.navigationMenus.onboardingGuide',
      ],
    },
    {
      scenario: 'teacher learner',
      surface: 'learner' as const,
      isCreator: true,
      sceneLabel: 'component.menus.navigationMenus.adminConsole',
      excludedSceneLabels: [
        'component.menus.navigationMenus.createCourse',
        'component.menus.navigationMenus.onboardingGuide',
      ],
    },
    {
      scenario: 'admin',
      surface: 'admin' as const,
      isCreator: false,
      sceneLabel: null,
      excludedSceneLabels: [
        'component.menus.navigationMenus.createCourse',
        'component.menus.navigationMenus.adminConsole',
      ],
    },
  ])(
    'renders shared rows in order with only the $scenario scene entry',
    ({ surface, isCreator, sceneLabel, excludedSceneLabels }) => {
      mockUserStoreState.userInfo = {
        mobile: '13800000000',
        email: 'user@example.com',
        is_creator: isCreator,
      };

      render(
        <MainMenuModal
          open
          onClose={jest.fn()}
          onPersonalInfoClick={jest.fn()}
          surface={surface}
        />,
      );

      const personalInfoButton = screen.getByRole('button', {
        name: 'component.menus.navigationMenus.personalInfo',
      });
      const menuText = personalInfoButton.parentElement?.textContent ?? '';
      const expectedLabels = [
        'component.menus.navigationMenus.personalInfo',
        'module.settings.setPassword',
        ...(sceneLabel ? [sceneLabel] : []),
        'component.menus.navigationMenus.language',
        'module.user.logout',
      ];
      const positions = expectedLabels.map(label => menuText.indexOf(label));

      expect(positions.every(position => position >= 0)).toBe(true);
      expect(positions).toEqual([...positions].sort((a, b) => a - b));
      expect(screen.getByTestId('language-select')).toHaveAttribute(
        'data-analytics-surface',
        surface === 'admin' ? 'admin_menu' : 'learner_menu',
      );
      expect(
        screen.getByRole('button', { name: 'module.settings.setPassword' }),
      ).toBeInTheDocument();
      if (sceneLabel) {
        expect(
          screen.getByRole('button', { name: sceneLabel }),
        ).toBeInTheDocument();
      }
      excludedSceneLabels.forEach(excludedSceneLabel => {
        expect(screen.queryByText(excludedSceneLabel)).not.toBeInTheDocument();
      });
    },
  );

  test('opens set password from the unified admin menu', () => {
    render(
      <MainMenuModal
        open
        onClose={jest.fn()}
        onPersonalInfoClick={jest.fn()}
        surface='admin'
      />,
    );

    expect(
      screen.queryByText('component.menus.navigationMenus.createCourse'),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.setPassword' }),
    );

    expect(screen.getByTestId('set-password-modal')).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenCalledWith('USER_MENU_SET_PASSWORD', {});
  });

  test.each(['learner', 'admin'] as const)(
    'shows login instead of logout on the %s surface for guests',
    surface => {
      mockUserStoreState.isLoggedIn = false;

      render(
        <MainMenuModal
          open
          onClose={jest.fn()}
          onPersonalInfoClick={jest.fn()}
          surface={surface}
        />,
      );

      expect(screen.getByText('module.user.login')).toBeInTheDocument();
      expect(screen.queryByText('module.user.logout')).not.toBeInTheDocument();
    },
  );

  test('does not show an onboarding entry in the admin menu', () => {
    render(
      <MainMenuModal
        open
        onClose={jest.fn()}
        onPersonalInfoClick={jest.fn()}
        surface='admin'
      />,
    );

    expect(
      screen.queryByText('component.menus.navigationMenus.onboardingGuide'),
    ).not.toBeInTheDocument();
  });

  test('hides set password entry when password login is unavailable', () => {
    mockEnvState.loginMethodsEnabled = ['phone'];

    render(
      <MainMenuModal
        open
        onClose={jest.fn()}
        onPersonalInfoClick={jest.fn()}
        surface='admin'
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
        onPersonalInfoClick={jest.fn()}
        surface='admin'
      />,
    );

    expect(
      screen.queryByText('module.settings.setPassword'),
    ).not.toBeInTheDocument();
  });

  test('closes the menu before opening personalization settings', () => {
    const calls: string[] = [];

    render(
      <MainMenuModal
        open
        onClose={() => calls.push('close-menu')}
        onPersonalInfoClick={() => calls.push('open-profile')}
        surface='admin'
      />,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'component.menus.navigationMenus.personalInfo',
      }),
    );

    expect(calls).toEqual(['close-menu', 'open-profile']);
    expect(mockTrackEvent).toHaveBeenCalledWith('USER_MENU_PERSONALIZED', {});
  });
});
