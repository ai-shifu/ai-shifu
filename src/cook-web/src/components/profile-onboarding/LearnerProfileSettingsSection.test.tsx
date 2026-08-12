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
  getLearnerProfile,
  updateLearnerProfile,
} from '@/api/learnerProfile';
import LearnerProfileSettingsSection, {
  type LearnerProfileSettingsHandle,
} from './LearnerProfileSettingsSection';
import { LEARNER_PROFILE_CHANGED_EVENT } from '@/lib/learnerProfileEvents';
import enProfile from '../../../../i18n/en-US/modules/profile-onboarding.json';
import frProfile from '../../../../i18n/fr-FR/modules/profile-onboarding.json';
import zhProfile from '../../../../i18n/zh-CN/modules/profile-onboarding.json';

const mockToast = jest.fn();
let mockLanguage = 'en-US';
let mockResolvedLanguage = 'en-US';
const translateKey = (
  key: string,
  params?: Record<string, string | number>,
) => {
  if (key === 'module.profileOnboarding.characterCount') {
    return `${params?.count} / ${params?.max}`;
  }
  if (key === 'module.profileOnboarding.characterCountOverLimit') {
    return `${params?.count} characters; limit ${params?.max}`;
  }
  if (key === 'module.profileOnboarding.settings.updatedAt') {
    return `updated:${params?.time}`;
  }
  return key;
};
let mockT = translateKey;

jest.mock('@/api/learnerProfile', () => ({
  clearLearnerProfile: jest.fn(),
  getLearnerProfile: jest.fn(),
  updateLearnerProfile: jest.fn(),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockT,
    i18n: {
      language: mockLanguage,
      resolvedLanguage: mockResolvedLanguage,
    },
  }),
}));

const mockGetLearnerProfile = getLearnerProfile as jest.Mock;
const mockUpdateLearnerProfile = updateLearnerProfile as jest.Mock;
const mockClearLearnerProfile = clearLearnerProfile as jest.Mock;

describe('LearnerProfileSettingsSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockT = translateKey;
    mockLanguage = 'en-US';
    mockResolvedLanguage = 'en-US';
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '现有学习画像',
      learner_profile_updated_at: null,
      has_learner_profile: true,
      max_length: 1000,
    });
  });

  test('limits clear confirmation to the canonical introduction', () => {
    expect(enProfile.settings.clearDescription).toContain('this introduction');
    expect(enProfile.settings.clearDescription).not.toContain('these details');
    expect(frProfile.settings.clearDescription).toContain('cette présentation');
    expect(frProfile.settings.clearDescription).not.toContain(
      'ces informations',
    );
    expect(zhProfile.settings.clearDescription).toContain('这段介绍');
    expect(zhProfile.settings.clearDescription).not.toContain('这些信息');
  });

  test('explains how to remove an introduction in every language', () => {
    expect(enProfile.settings.emptyProfile).toContain(enProfile.settings.clear);
    expect(frProfile.settings.emptyProfile).toContain(frProfile.settings.clear);
    expect(zhProfile.settings.emptyProfile).toContain(zhProfile.settings.clear);
  });

  test('explains that teacher course design wins conflicting requests', () => {
    expect(zhProfile.settings.description).toContain(
      '真人老师为课程做出的设定',
    );
    expect(zhProfile.settings.description).toContain('以真人老师的设定为准');
    expect(enProfile.settings.description).toContain(
      'course design set by the human teacher',
    );
    expect(enProfile.settings.description).toContain(
      "follow the human teacher's design",
    );
    expect(frProfile.settings.description).toContain(
      'cadre défini pour le cours par l’enseignant humain',
    );
    expect(frProfile.settings.description).toContain('suivra ce cadre');
  });

  test('loads and directly saves an edited profile', async () => {
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    mockUpdateLearnerProfile.mockResolvedValue({
      learner_profile: '更新后的学习画像',
      learner_profile_updated_at: null,
      has_learner_profile: true,
      max_length: 1000,
    });
    render(<LearnerProfileSettingsSection />);

    const editor = await screen.findByDisplayValue('现有学习画像');
    fireEvent.change(editor, { target: { value: '更新后的学习画像' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('更新后的学习画像');
    });
    expect(mockToast).not.toHaveBeenCalled();
    expect(onProfileChanged).toHaveBeenCalledTimes(1);
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('formats the update timestamp with the resolved interface language', async () => {
    const updatedAt = '2026-08-03T01:02:03Z';
    mockLanguage = 'en-US';
    mockResolvedLanguage = 'fr-FR';
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: 'Profil existant',
      learner_profile_updated_at: updatedAt,
      has_learner_profile: true,
      max_length: 1000,
    });

    render(<LearnerProfileSettingsSection />);

    const expectedTime = new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(updatedAt));
    expect(
      await screen.findByText(`updated:${expectedTime}`),
    ).toBeInTheDocument();
  });

  test('preserves an unsaved draft when the interface language changes', async () => {
    const { rerender } = render(
      <LearnerProfileSettingsSection draftStorageScope='user-a' />,
    );
    const editor = await screen.findByDisplayValue('现有学习画像');
    fireEvent.change(editor, { target: { value: '尚未保存的学习画像' } });

    mockLanguage = 'fr-FR';
    mockResolvedLanguage = 'fr-FR';
    mockT = (key, params) => translateKey(key, params);
    rerender(<LearnerProfileSettingsSection draftStorageScope='user-a' />);

    expect(screen.getByRole('textbox')).toHaveValue('尚未保存的学习画像');
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1);
  });

  test('keeps editing disabled until a failed profile load is retried', async () => {
    mockGetLearnerProfile
      .mockRejectedValueOnce(new Error('load failed'))
      .mockResolvedValueOnce({
        learner_profile: '重新加载的学习画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      });
    render(<LearnerProfileSettingsSection />);

    const editor = await screen.findByLabelText(
      'module.profileOnboarding.profileLabel',
    );
    expect(editor).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    ).toBeDisabled();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.retry',
      }),
    );

    expect(await screen.findByDisplayValue('重新加载的学习画像')).toBeEnabled();
  });

  test('lets the parent save continue when an older backend cannot load profiles', async () => {
    const settingsRef = React.createRef<LearnerProfileSettingsHandle>();
    mockGetLearnerProfile.mockRejectedValue(new Error('404'));
    render(<LearnerProfileSettingsSection ref={settingsRef} />);

    await screen.findByRole('button', {
      name: 'module.profileOnboarding.settings.retry',
    });
    let saved = false;
    await act(async () => {
      saved = (await settingsRef.current?.saveIfDirty()) ?? false;
    });

    expect(saved).toBe(true);
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
  });

  test('reloads for a new account and ignores the previous response', async () => {
    let resolveFirstProfile: (value: {
      learner_profile: string;
      learner_profile_updated_at: null;
      has_learner_profile: boolean;
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
        has_learner_profile: true,
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
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveFirstProfile({
        learner_profile: '账号 A 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      });
    });
    expect(screen.queryByDisplayValue('账号 A 的画像')).not.toBeInTheDocument();
    expect(screen.getByDisplayValue('账号 B 的画像')).toBeInTheDocument();
  });

  test('ignores a save response that arrives after account A unmounts', async () => {
    let resolveSave: (value: {
      learner_profile: string;
      learner_profile_updated_at: null;
      has_learner_profile: boolean;
      max_length: number;
    }) => void = () => undefined;
    mockGetLearnerProfile
      .mockResolvedValueOnce({
        learner_profile: '账号 A 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      })
      .mockResolvedValueOnce({
        learner_profile: '账号 B 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      });
    mockUpdateLearnerProfile.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveSave = resolve;
        }),
    );
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);

    const accountA = render(
      <LearnerProfileSettingsSection draftStorageScope='user-a' />,
    );
    fireEvent.change(await screen.findByDisplayValue('账号 A 的画像'), {
      target: { value: '账号 A 的新画像' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledTimes(1),
    );
    accountA.unmount();

    render(<LearnerProfileSettingsSection draftStorageScope='user-b' />);
    expect(
      await screen.findByDisplayValue('账号 B 的画像'),
    ).toBeInTheDocument();
    await act(async () => {
      resolveSave({
        learner_profile: '账号 A 的新画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      });
    });

    expect(screen.getByDisplayValue('账号 B 的画像')).toBeInTheDocument();
    expect(mockToast).not.toHaveBeenCalled();
    expect(onProfileChanged).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('ignores a rejected save after account A unmounts', async () => {
    let rejectSave: (reason: Error) => void = () => undefined;
    mockGetLearnerProfile
      .mockResolvedValueOnce({
        learner_profile: '账号 A 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      })
      .mockResolvedValueOnce({
        learner_profile: '账号 B 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      });
    mockUpdateLearnerProfile.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectSave = reject;
        }),
    );
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);

    const accountA = render(
      <LearnerProfileSettingsSection draftStorageScope='user-a' />,
    );
    fireEvent.change(await screen.findByDisplayValue('账号 A 的画像'), {
      target: { value: '账号 A 的新画像' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledTimes(1),
    );
    accountA.unmount();

    render(<LearnerProfileSettingsSection draftStorageScope='user-b' />);
    expect(
      await screen.findByDisplayValue('账号 B 的画像'),
    ).toBeInTheDocument();
    await act(async () => {
      rejectSave(new Error('late save failed'));
    });

    expect(screen.getByDisplayValue('账号 B 的画像')).toBeInTheDocument();
    expect(mockToast).not.toHaveBeenCalled();
    expect(onProfileChanged).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('ignores a clear response that arrives after account A unmounts', async () => {
    let resolveClear: (value: {
      learner_profile: string;
      learner_profile_updated_at: null;
      has_learner_profile: boolean;
      max_length: number;
    }) => void = () => undefined;
    mockGetLearnerProfile
      .mockResolvedValueOnce({
        learner_profile: '账号 A 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      })
      .mockResolvedValueOnce({
        learner_profile: '账号 B 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      });
    mockClearLearnerProfile.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveClear = resolve;
        }),
    );
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);

    const accountA = render(
      <LearnerProfileSettingsSection draftStorageScope='user-a' />,
    );
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
    await waitFor(() =>
      expect(mockClearLearnerProfile).toHaveBeenCalledTimes(1),
    );
    accountA.unmount();

    render(<LearnerProfileSettingsSection draftStorageScope='user-b' />);
    expect(
      await screen.findByDisplayValue('账号 B 的画像'),
    ).toBeInTheDocument();
    await act(async () => {
      resolveClear({
        learner_profile: '',
        learner_profile_updated_at: null,
        has_learner_profile: false,
        max_length: 1000,
      });
    });

    expect(screen.getByDisplayValue('账号 B 的画像')).toBeInTheDocument();
    expect(mockToast).not.toHaveBeenCalled();
    expect(onProfileChanged).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('ignores a rejected clear after account A unmounts', async () => {
    let rejectClear: (reason: Error) => void = () => undefined;
    mockGetLearnerProfile
      .mockResolvedValueOnce({
        learner_profile: '账号 A 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      })
      .mockResolvedValueOnce({
        learner_profile: '账号 B 的画像',
        learner_profile_updated_at: null,
        has_learner_profile: true,
        max_length: 1000,
      });
    mockClearLearnerProfile.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectClear = reject;
        }),
    );
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);

    const accountA = render(
      <LearnerProfileSettingsSection draftStorageScope='user-a' />,
    );
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
    await waitFor(() =>
      expect(mockClearLearnerProfile).toHaveBeenCalledTimes(1),
    );
    accountA.unmount();

    render(<LearnerProfileSettingsSection draftStorageScope='user-b' />);
    expect(
      await screen.findByDisplayValue('账号 B 的画像'),
    ).toBeInTheDocument();
    await act(async () => {
      rejectClear(new Error('late clear failed'));
    });

    expect(screen.getByDisplayValue('账号 B 的画像')).toBeInTheDocument();
    expect(mockToast).not.toHaveBeenCalled();
    expect(onProfileChanged).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('exposes a save operation for the page-wide settings action', async () => {
    const settingsRef = React.createRef<LearnerProfileSettingsHandle>();
    mockUpdateLearnerProfile.mockResolvedValue({
      learner_profile: '页脚保存后的画像',
      learner_profile_updated_at: null,
      has_learner_profile: true,
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

  test('shows inline guidance when page-wide save finds an empty introduction', async () => {
    const settingsRef = React.createRef<LearnerProfileSettingsHandle>();
    render(<LearnerProfileSettingsSection ref={settingsRef} />);

    fireEvent.change(await screen.findByDisplayValue('现有学习画像'), {
      target: { value: '   ' },
    });
    let saved = true;
    await act(async () => {
      saved = (await settingsRef.current?.saveIfDirty()) ?? true;
    });

    expect(saved).toBe(false);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'module.profileOnboarding.settings.emptyProfile',
    );
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
  });

  test('requires explicit confirmation before clearing the profile', async () => {
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    mockClearLearnerProfile.mockResolvedValue({
      learner_profile: '',
      learner_profile_updated_at: null,
      has_learner_profile: false,
      max_length: 1000,
    });
    render(<LearnerProfileSettingsSection />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.settings.clear',
      }),
    );
    expect(mockClearLearnerProfile).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.confirmClear',
      }),
    );

    await waitFor(() => {
      expect(mockClearLearnerProfile).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => expect(onProfileChanged).toHaveBeenCalledTimes(1));
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.profileOnboarding.settings.clearSuccess',
    });
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('does not truncate an oversized Unicode edit', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '旧画像',
      learner_profile_updated_at: null,
      has_learner_profile: true,
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
  });

  test('validates and saves the trimmed Unicode code-point length', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '旧画像',
      learner_profile_updated_at: null,
      has_learner_profile: true,
      max_length: 3,
    });
    mockUpdateLearnerProfile.mockResolvedValue({
      learner_profile: 'A😀你',
      learner_profile_updated_at: null,
      has_learner_profile: true,
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
