import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {
  clearLearnerProfile,
  completeProfileOnboarding,
  getLearnerProfile,
  getProfileOnboarding,
  updateLearnerProfile,
} from '@/c-api/user';
import LearnerProfileSettingsSection, {
  type LearnerProfileSettingsHandle,
} from './LearnerProfileSettingsSection';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const COMPLETE_RERUN_LABEL = 'complete learner profile rerun';
const mockT = (key: string, params?: Record<string, string | number>) => {
  if (key === 'module.profileOnboarding.characterCount') {
    return `${params?.count} / ${params?.max}`;
  }
  if (key === 'module.profileOnboarding.characterCountOverLimit') {
    return `${params?.count} characters; limit ${params?.max}`;
  }
  return key;
};

jest.mock('@/c-api/user', () => {
  return {
    clearLearnerProfile: jest.fn(),
    completeProfileOnboarding: jest.fn(),
    getLearnerProfile: jest.fn(),
    getProfileOnboarding: jest.fn(),
    isProfileOnboardingV2Status: (value: unknown) =>
      typeof value === 'object' &&
      value !== null &&
      'contract_version' in value &&
      value.contract_version === 'profile-v2',
    updateLearnerProfile: jest.fn(),
  };
});

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockT,
  }),
}));

jest.mock('./ProfileOnboardingModal', () => {
  const actual = jest.requireActual('./ProfileOnboardingModal');
  return {
    ...actual,
    __esModule: true,
    default: ({
      open,
      sessionIntent,
      errorMessage,
      onComplete,
    }: {
      open: boolean;
      sessionIntent?: string;
      errorMessage?: string;
      onComplete: (
        learnerProfile: string,
        source: 'guided',
        sessionId: string,
      ) => Promise<boolean>;
    }) =>
      open ? (
        <div
          data-testid='rerun-modal'
          data-session-intent={sessionIntent}
        >
          <button
            type='button'
            onClick={() => {
              void onComplete('重新生成的学习画像', 'guided', 'session-2');
            }}
          >
            {COMPLETE_RERUN_LABEL}
          </button>
          {errorMessage ? <div role='alert'>{errorMessage}</div> : null}
        </div>
      ) : null,
  };
});

const mockGetLearnerProfile = getLearnerProfile as jest.Mock;
const mockGetOnboarding = getProfileOnboarding as jest.Mock;
const mockUpdateLearnerProfile = updateLearnerProfile as jest.Mock;
const mockClearLearnerProfile = clearLearnerProfile as jest.Mock;
const mockCompleteProfileOnboarding = completeProfileOnboarding as jest.Mock;
const profileV2Status = (overrides: Record<string, unknown> = {}) => ({
  contract_version: 'profile-v2',
  enabled: false,
  should_show: false,
  presentation: 'hidden',
  legacy_handled: false,
  has_learner_profile: true,
  learner_profile_updated_at: null,
  max_length: 1000,
  config_revision: 1,
  guided_available: false,
  ...overrides,
});

describe('LearnerProfileSettingsSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '现有学习画像',
      learner_profile_updated_at: null,
      max_length: 1000,
    });
    mockGetOnboarding.mockResolvedValue(profileV2Status());
    mockCompleteProfileOnboarding.mockResolvedValue({ completed: true });
  });

  test('keeps direct edit available while the collection kill switch hides rerun', async () => {
    mockUpdateLearnerProfile.mockResolvedValue({
      learner_profile: '更新后的学习画像',
      learner_profile_updated_at: null,
      max_length: 1000,
    });
    render(<LearnerProfileSettingsSection />);

    const editor = await screen.findByDisplayValue('现有学习画像');
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.settings.rerun',
      }),
    ).not.toBeInTheDocument();

    fireEvent.change(editor, { target: { value: '更新后的学习画像' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('更新后的学习画像');
    });
  });

  test('shows voluntary rerun only while collection is enabled', async () => {
    mockGetOnboarding.mockResolvedValue(
      profileV2Status({
        enabled: true,
        should_show: false,
        has_learner_profile: false,
        guided_available: true,
      }),
    );
    render(<LearnerProfileSettingsSection />);

    const rerun = await screen.findByRole('button', {
      name: 'module.profileOnboarding.settings.rerun',
    });
    fireEvent.click(rerun);
    expect(screen.getByTestId('rerun-modal')).toHaveAttribute(
      'data-session-intent',
      'settings',
    );
  });

  test('hides rerun until a first-time settings user saves a profile', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '',
      learner_profile_updated_at: null,
      max_length: 1000,
    });
    mockGetOnboarding.mockResolvedValue(
      profileV2Status({
        enabled: true,
        should_show: true,
        has_learner_profile: false,
        guided_available: true,
      }),
    );
    mockUpdateLearnerProfile.mockResolvedValue({
      learner_profile: '首次保存的学习画像',
      learner_profile_updated_at: null,
      max_length: 1000,
    });

    render(<LearnerProfileSettingsSection />);

    const editor = await screen.findByLabelText(
      'module.profileOnboarding.profileLabel',
    );
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.settings.rerun',
      }),
    ).not.toBeInTheDocument();

    fireEvent.change(editor, {
      target: { value: '首次保存的学习画像' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    );

    expect(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.settings.rerun',
      }),
    ).toBeInTheDocument();
  });

  test('reloads for a new account scope and ignores the previous response', async () => {
    let resolveFirstProfile: (value: {
      learner_profile: string;
      learner_profile_updated_at: null;
      max_length: number;
    }) => void = () => undefined;
    mockGetLearnerProfile
      .mockImplementationOnce(
        () =>
          new Promise(resolve => {
            resolveFirstProfile = resolve;
          }),
      )
      .mockResolvedValueOnce({
        learner_profile: '账号 B 的画像',
        learner_profile_updated_at: null,
        max_length: 1000,
      });

    const { rerender } = render(
      <LearnerProfileSettingsSection draftStorageScope='user-a' />,
    );
    await waitFor(() => expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1));

    rerender(<LearnerProfileSettingsSection draftStorageScope='user-b' />);
    expect(
      await screen.findByDisplayValue('账号 B 的画像'),
    ).toBeInTheDocument();

    await act(async () => {
      resolveFirstProfile({
        learner_profile: '账号 A 的画像',
        learner_profile_updated_at: null,
        max_length: 1000,
      });
    });
    expect(screen.queryByDisplayValue('账号 A 的画像')).not.toBeInTheDocument();
    expect(screen.getByDisplayValue('账号 B 的画像')).toBeInTheDocument();
  });

  test('keeps the rerun modal open when the saved profile cannot be refreshed', async () => {
    mockGetOnboarding.mockResolvedValue(
      profileV2Status({
        enabled: true,
        guided_available: true,
      }),
    );
    render(<LearnerProfileSettingsSection draftStorageScope='user-rerun' />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.settings.rerun',
      }),
    );
    mockGetLearnerProfile.mockRejectedValueOnce(new Error('refresh failed'));
    fireEvent.click(screen.getByRole('button', { name: COMPLETE_RERUN_LABEL }));

    await waitFor(() => {
      expect(mockCompleteProfileOnboarding).toHaveBeenCalledWith({
        learner_profile: '重新生成的学习画像',
        trigger_source: 'guided',
        session_id: 'session-2',
      });
    });
    expect(await screen.findByTestId('rerun-modal')).toBeInTheDocument();
    expect(await screen.findAllByText('refresh failed')).not.toHaveLength(0);
    expect(mockToast).not.toHaveBeenCalledWith({
      title: 'module.profileOnboarding.settings.regenerateSuccess',
    });
  });

  test('exposes a save operation for the page-wide settings action', async () => {
    const settingsRef = React.createRef<LearnerProfileSettingsHandle>();
    mockUpdateLearnerProfile.mockResolvedValue({
      learner_profile: '页脚保存后的画像',
      learner_profile_updated_at: null,
      max_length: 1000,
    });
    render(<LearnerProfileSettingsSection ref={settingsRef} />);

    fireEvent.change(await screen.findByDisplayValue('现有学习画像'), {
      target: { value: '页脚保存后的画像' },
    });
    let saved = false;
    await act(async () => {
      saved = (await settingsRef.current?.saveIfDirty()) ?? false;
    });

    expect(saved).toBe(true);
    expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('页脚保存后的画像');
  });

  test('hides rerun when an old backend omits the v2 contract version', async () => {
    mockGetOnboarding.mockResolvedValue({
      enabled: true,
      should_show: true,
      markdownflow: '?[Name?]',
    });

    render(<LearnerProfileSettingsSection />);

    await screen.findByDisplayValue('现有学习画像');
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.settings.rerun',
      }),
    ).not.toBeInTheDocument();
  });

  test('requires explicit confirmation before clearing the profile', async () => {
    mockClearLearnerProfile.mockResolvedValue({
      learner_profile: '',
      learner_profile_updated_at: null,
      max_length: 1000,
    });
    render(<LearnerProfileSettingsSection />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.settings.clear',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.confirmClear',
      }),
    );

    await waitFor(() => {
      expect(mockClearLearnerProfile).toHaveBeenCalledTimes(1);
    });
  });

  test('does not truncate an oversized direct edit', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '旧画像',
      learner_profile_updated_at: null,
      max_length: 3,
    });
    render(<LearnerProfileSettingsSection />);

    const editor = await screen.findByDisplayValue('旧画像');
    fireEvent.change(editor, { target: { value: 'A😀你X' } });

    expect(editor).toHaveValue('A😀你X');
    expect(screen.getByText('4 characters; limit 3')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    ).toBeDisabled();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
  });

  test('validates and saves the trimmed profile length', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '旧画像',
      learner_profile_updated_at: null,
      max_length: 3,
    });
    mockUpdateLearnerProfile.mockResolvedValue({
      learner_profile: 'A😀你',
      learner_profile_updated_at: null,
      max_length: 3,
    });
    render(<LearnerProfileSettingsSection />);

    const editor = await screen.findByDisplayValue('旧画像');
    fireEvent.change(editor, { target: { value: '  A😀你  ' } });

    expect(screen.getByText('3 / 3')).toBeInTheDocument();
    const saveButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.settings.save',
    });
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('A😀你');
    });
  });
});
