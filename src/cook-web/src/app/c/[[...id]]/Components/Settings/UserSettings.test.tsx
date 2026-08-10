import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { getUserProfile, updateUserProfile } from '@/c-api/user';
import { UserSettings } from './UserSettings';

const mockSaveLearnerProfile = jest.fn();
const mockRefreshUserInfo = jest.fn();
let mockUserId = 'settings-user';

jest.mock('@/c-api/user', () => ({
  getUserProfile: jest.fn(),
  updateUserProfile: jest.fn(),
}));

jest.mock('@/store', () => ({
  useUserStore: (selector: (state: unknown) => unknown) =>
    selector({
      refreshUserInfo: mockRefreshUserInfo,
      userInfo: { user_id: mockUserId },
    }),
}));

jest.mock('@/c-store/envStore', () => ({
  useEnvStore: (selector: (state: unknown) => unknown) =>
    selector({ courseId: 'course-1' }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN' },
  }),
}));

jest.mock(
  '@/components/profile-onboarding/LearnerProfileSettingsSection',
  () => {
    const ReactModule = jest.requireActual('react') as typeof React;
    return {
      __esModule: true,
      default: ReactModule.forwardRef(
        function MockLearnerProfileSettings(_props, ref) {
          ReactModule.useImperativeHandle(ref, () => ({
            saveIfDirty: mockSaveLearnerProfile,
          }));
          return ReactModule.createElement('div', {
            'data-testid': 'learner-profile-settings',
          });
        },
      ),
    };
  },
);

jest.mock(
  './SettingHeader',
  () =>
    function MockSettingHeader() {
      return <div />;
    },
);
jest.mock(
  './ChangeAvatar',
  () =>
    function MockChangeAvatar() {
      return <div />;
    },
);
jest.mock(
  './SexSettingModal',
  () =>
    function MockSexSettingModal() {
      return null;
    },
);
jest.mock(
  './BirthdaySettingModal',
  () =>
    function MockBirthdaySettingModal() {
      return null;
    },
);
jest.mock('./SettingInputElement', () => ({
  SettingInputElement: function MockSettingInputElement() {
    return <div />;
  },
}));
jest.mock(
  './SettingSelectElement',
  () =>
    function MockSettingSelectElement() {
      return <div />;
    },
);
jest.mock(
  './DynamicSettingItem',
  () =>
    function MockDynamicSettingItem({
      settingItem,
    }: {
      settingItem: { key: string };
    }) {
      return <div>{settingItem.key}</div>;
    },
);

const mockGetUserProfile = getUserProfile as jest.Mock;
const mockUpdateUserProfile = updateUserProfile as jest.Mock;

describe('UserSettings learner profile save integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUserId = 'settings-user';
    mockGetUserProfile.mockResolvedValue([]);
    mockUpdateUserProfile.mockResolvedValue(undefined);
    mockRefreshUserInfo.mockResolvedValue(undefined);
  });

  test('keeps settings open when the learner profile draft cannot be saved', async () => {
    const onClose = jest.fn();
    mockSaveLearnerProfile.mockResolvedValue(false);
    render(
      <UserSettings
        onHomeClick={jest.fn()}
        className=''
        onClose={onClose}
      />,
    );

    await screen.findByTestId('learner-profile-settings');
    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.save' }),
    );

    await waitFor(() => {
      expect(mockSaveLearnerProfile).toHaveBeenCalledTimes(1);
    });
    expect(mockRefreshUserInfo).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  test('keeps legacy background and style fields visible with course fields', async () => {
    mockGetUserProfile.mockResolvedValue([
      { key: 'sys_user_background', value: '产品经理' },
      { key: 'sys_user_style', value: '简洁' },
      { key: 'course_learning_goal', value: '完成项目' },
    ]);

    render(
      <UserSettings
        onHomeClick={jest.fn()}
        className=''
        onClose={jest.fn()}
      />,
    );

    expect(await screen.findByText('course_learning_goal')).toBeInTheDocument();
    expect(screen.getByText('sys_user_background')).toBeInTheDocument();
    expect(screen.getByText('sys_user_style')).toBeInTheDocument();
  });

  test('closes settings after both parent fields and learner profile save', async () => {
    const onClose = jest.fn();
    mockSaveLearnerProfile.mockResolvedValue(true);
    render(
      <UserSettings
        onHomeClick={jest.fn()}
        className=''
        onClose={onClose}
      />,
    );

    await screen.findByTestId('learner-profile-settings');
    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.save' }),
    );

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(mockUpdateUserProfile).toHaveBeenCalledTimes(1);
    expect(mockSaveLearnerProfile).toHaveBeenCalledTimes(1);
    expect(mockRefreshUserInfo).toHaveBeenCalledTimes(1);
  });

  test('does not mount or await learner profile settings in basic info mode', async () => {
    const onClose = jest.fn();
    mockSaveLearnerProfile.mockImplementation(() => new Promise(() => {}));
    render(
      <UserSettings
        onHomeClick={jest.fn()}
        className=''
        onClose={onClose}
        isBasicInfo
      />,
    );

    expect(
      screen.queryByTestId('learner-profile-settings'),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.save' }),
    );

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(mockSaveLearnerProfile).not.toHaveBeenCalled();
    expect(mockRefreshUserInfo).toHaveBeenCalledTimes(1);
  });

  test('closes personal settings when unavailable learner profiles no-op on save', async () => {
    const onClose = jest.fn();
    mockSaveLearnerProfile.mockResolvedValue(true);
    render(
      <UserSettings
        onHomeClick={jest.fn()}
        className=''
        onClose={onClose}
      />,
    );

    await screen.findByTestId('learner-profile-settings');
    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.save' }),
    );

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(mockUpdateUserProfile).toHaveBeenCalledTimes(1);
    expect(mockRefreshUserInfo).toHaveBeenCalledTimes(1);
  });

  test('stops an in-flight save when the active account changes', async () => {
    const onClose = jest.fn();
    let resolveProfileUpdate: (() => void) | undefined;
    const profileUpdate = new Promise<void>(resolve => {
      resolveProfileUpdate = resolve;
    });
    mockUpdateUserProfile.mockReturnValue(profileUpdate);
    mockSaveLearnerProfile.mockResolvedValue(true);

    const { rerender } = render(
      <UserSettings
        onHomeClick={jest.fn()}
        className=''
        onClose={onClose}
      />,
    );

    await screen.findByTestId('learner-profile-settings');
    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.save' }),
    );
    await waitFor(() => {
      expect(mockUpdateUserProfile).toHaveBeenCalledTimes(1);
    });

    mockUserId = 'other-settings-user';
    rerender(
      <UserSettings
        onHomeClick={jest.fn()}
        className=''
        onClose={onClose}
      />,
    );
    await act(async () => {
      resolveProfileUpdate?.();
      await profileUpdate;
    });

    expect(mockSaveLearnerProfile).not.toHaveBeenCalled();
    expect(mockRefreshUserInfo).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
