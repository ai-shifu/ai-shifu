import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { getLearnerProfile, updateLearnerProfile } from '@/api/learnerProfile';
import { LEARNER_PROFILE_CHANGED_EVENT } from '@/lib/learnerProfileEvents';
import LearnerProfileDialog from './LearnerProfileDialog';
import enProfile from '../../../../i18n/en-US/modules/profile-onboarding.json';
import frProfile from '../../../../i18n/fr-FR/modules/profile-onboarding.json';
import zhProfile from '../../../../i18n/zh-CN/modules/profile-onboarding.json';

const mockToast = jest.fn();
const translateKey = (
  key: string,
  params?: Record<string, string | number>,
) => {
  if (key === 'module.profileOnboarding.characterCount') {
    return `${params?.count} / ${params?.max}`;
  }
  if (key === 'module.profileOnboarding.characterCountOverLimit') {
    return `${params?.count} / ${params?.max} over limit`;
  }
  return key;
};
let mockT = translateKey;
let mockLanguage = 'en-US';

jest.mock('@/api/learnerProfile', () => ({
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
      resolvedLanguage: mockLanguage,
    },
  }),
}));

const mockGetLearnerProfile = getLearnerProfile as jest.Mock;
const mockUpdateLearnerProfile = updateLearnerProfile as jest.Mock;

const existingProfile = {
  learner_profile: 'Existing learner introduction',
  learner_profile_updated_at: '2026-08-11T01:00:00Z',
  has_learner_profile: true,
  max_length: 1000,
};

const renderDialog = (
  overrides: Partial<React.ComponentProps<typeof LearnerProfileDialog>> = {},
) => {
  const props: React.ComponentProps<typeof LearnerProfileDialog> = {
    open: true,
    mode: 'settings',
    draftStorageScope: 'user-a',
    onClose: jest.fn(),
    ...overrides,
  };
  return { props, ...render(<LearnerProfileDialog {...props} />) };
};

describe('LearnerProfileDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockT = translateKey;
    mockLanguage = 'en-US';
    mockGetLearnerProfile.mockResolvedValue(existingProfile);
  });

  test('shows one canonical introduction without legacy fields or parsed nickname UI', async () => {
    renderDialog({ mode: 'onboarding' });

    await screen.findByDisplayValue(existingProfile.learner_profile);
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    expect(screen.queryByText('sys_user_nickname')).not.toBeInTheDocument();
    expect(screen.queryByText('sys_user_background')).not.toBeInTheDocument();
    expect(screen.queryByText('sys_user_style')).not.toBeInTheDocument();
    expect(screen.queryByText(/parsed nickname/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.later',
      }),
    ).toBeInTheDocument();

    expect(zhProfile.dialog.onboardingTitle).toContain('AI 老师');
    expect(zhProfile.dialog.description).toContain('AI 老师');
    expect(zhProfile.dialog.chips.teaching.text).toContain('AI 老师');
    expect(zhProfile.dialog.writingGuideTeaching).toContain('AI 老师');
    expect(JSON.stringify(zhProfile.dialog)).not.toContain('课程');
    expect(enProfile.dialog.description).toContain('AI teacher');
    expect(enProfile.dialog.chips.teaching.text).toContain('AI teacher');
    expect(enProfile.dialog.writingGuideTeaching).toContain('AI teacher');
    expect(JSON.stringify(enProfile.dialog)).not.toMatch(/\bcourses?\b/i);
    expect(frProfile.dialog.description).toContain('enseignant IA');
    expect(frProfile.dialog.chips.teaching.text).toContain('enseignant IA');
    expect(frProfile.dialog.writingGuideTeaching).toContain('enseignant IA');
    expect(JSON.stringify(frProfile.dialog)).not.toMatch(/\bcours\b/i);
  });

  test('uses a complete everyday placeholder in every language', () => {
    const zhPlaceholder = zhProfile.dialog.profilePlaceholder;
    const enPlaceholder = enProfile.dialog.profilePlaceholder;
    const frPlaceholder = frProfile.dialog.profilePlaceholder;

    for (const detail of [
      '可以叫我',
      '工作之余学习',
      '有一点基础',
      '日常工作和生活',
      '不知道从哪里开始',
      '核心概念',
      '分步骤',
      '贴近日常的例子',
      '容易踩的坑',
    ]) {
      expect(zhPlaceholder).toContain(detail);
    }
    expect(zhPlaceholder).not.toContain('产品经理');
    expect(zhPlaceholder).not.toContain('AI 产品');

    for (const detail of [
      'call me',
      'alongside work',
      'know a little',
      'everyday problems',
      'where to begin',
      'simple language',
      'walk through the steps',
      'everyday examples',
      'common pitfalls',
    ]) {
      expect(enPlaceholder).toContain(detail);
    }
    expect(enPlaceholder).not.toContain('AI products');

    for (const detail of [
      'm’appeler',
      'parallèle de mon travail',
      'connais un peu',
      'problèmes du quotidien',
      'par où commencer',
      'mots simples',
      'puis les étapes',
      'exemples familiers',
      'pièges fréquents',
    ]) {
      expect(frPlaceholder).toContain(detail);
    }
    expect(frPlaceholder).not.toContain('produits IA');
  });

  test('renders the centered contextual dialog with option-three guidance and actions', async () => {
    renderDialog({ mode: 'onboarding' });

    await screen.findByDisplayValue(existingProfile.learner_profile);
    const dialog = screen.getByRole('dialog');
    const editor = screen.getByRole('textbox');
    const heading = screen.getByText(
      'module.profileOnboarding.dialog.onboardingTitle',
    );
    const writingGuide = screen.getByTestId('learner-profile-writing-guide');
    const reassurance = screen.getByTestId('learner-profile-reassurance');
    const mobileHandle = screen.getByTestId('learner-profile-mobile-handle');
    const later = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.later',
    });
    const primaryAction = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveAndContinue',
    });
    const footer = later.parentElement;
    const overlay = Array.from(
      document.body.querySelectorAll('[data-state="open"]'),
    ).find(element => element.className.includes('z-[100]'));

    expect(dialog).toHaveClass(
      'h-[calc(100dvh-96px)]',
      'sm:max-w-[680px]',
      'sm:rounded-2xl',
    );
    expect(editor).toHaveClass('min-h-[215px]', 'sm:min-h-[185px]');
    expect(heading.parentElement).toHaveClass('text-center');
    expect(dialog.querySelector('svg.lucide-sparkles')).toBeNull();
    expect(mobileHandle).toHaveClass('sm:hidden');
    expect(writingGuide).toHaveTextContent(
      'module.profileOnboarding.dialog.writingGuideTitle',
    );
    expect(writingGuide).toHaveTextContent(
      'module.profileOnboarding.dialog.writingGuideIdentity',
    );
    expect(writingGuide).toHaveTextContent(
      'module.profileOnboarding.dialog.writingGuideGoals',
    );
    expect(writingGuide).toHaveTextContent(
      'module.profileOnboarding.dialog.writingGuideTeaching',
    );
    expect(reassurance).toHaveTextContent(
      'module.profileOnboarding.dialog.reassurance',
    );
    expect(overlay).toHaveClass('!bg-slate-950/45', 'backdrop-blur-[1px]');
    expect(footer).toHaveClass('sticky', 'bottom-0');
    expect(footer).toContainElement(primaryAction);
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.dialog.moreActions',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.clear'),
    ).not.toBeInTheDocument();
  });

  test('adds all optional prompt chips to and focuses the same textarea', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      ...existingProfile,
      learner_profile: '',
      has_learner_profile: false,
    });
    renderDialog();
    const editor = await screen.findByRole('textbox');

    for (const prompt of ['identity', 'goals', 'teaching']) {
      fireEvent.click(
        screen.getByRole('button', {
          name: `module.profileOnboarding.dialog.chips.${prompt}.label`,
        }),
      );
      expect(editor).toHaveFocus();
    }

    expect(editor).toHaveValue(
      [
        'module.profileOnboarding.dialog.chips.identity.text',
        'module.profileOnboarding.dialog.chips.goals.text',
        'module.profileOnboarding.dialog.chips.teaching.text',
      ].join('\n'),
    );
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
  });

  test('saves, refreshes consumers, and closes in order', async () => {
    const calls: string[] = [];
    const onClose = jest.fn((reason: 'dismiss' | 'saved') => {
      calls.push(`close:${reason}`);
    });
    const onSaved = jest.fn(async () => {
      calls.push('saved');
    });
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    mockUpdateLearnerProfile.mockResolvedValue({
      ...existingProfile,
      learner_profile: 'Updated learner introduction',
    });
    renderDialog({ onClose, onSaved });

    fireEvent.change(
      await screen.findByDisplayValue(existingProfile.learner_profile),
      { target: { value: 'Updated learner introduction' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(
        'Updated learner introduction',
      );
      expect(onClose).toHaveBeenCalledTimes(1);
    });
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(calls).toEqual(['saved', 'close:saved']);
    expect(onClose).toHaveBeenCalledWith('saved');
    expect(onProfileChanged).toHaveBeenCalledTimes(1);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.profileOnboarding.dialog.saveSuccess',
    });
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('keeps the editor protected after load failure and retries', async () => {
    mockGetLearnerProfile
      .mockRejectedValueOnce(new Error('load request failed'))
      .mockResolvedValueOnce(existingProfile);
    renderDialog();

    expect(await screen.findByText('load request failed')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeDisabled();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retry',
      }),
    );

    expect(
      await screen.findByDisplayValue(existingProfile.learner_profile),
    ).toBeEnabled();
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(2);
  });

  test('uses settings cancel and onboarding later for clean dismissal', async () => {
    const settingsClose = jest.fn();
    const { unmount } = renderDialog({ onClose: settingsClose });
    await screen.findByDisplayValue(existingProfile.learner_profile);
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.dialog.cancel',
        }),
      );
    });
    expect(settingsClose).toHaveBeenCalledWith('dismiss');
    unmount();

    const onboardingClose = jest.fn();
    renderDialog({ mode: 'onboarding', onClose: onboardingClose });
    await screen.findByDisplayValue(existingProfile.learner_profile);
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.dialog.later',
        }),
      );
    });
    expect(onboardingClose).toHaveBeenCalledWith('dismiss');
  });

  test('keeps onboarding open when dismiss fails and prevents duplicate requests', async () => {
    let rejectDismiss: (error: Error) => void = () => undefined;
    const onClose = jest
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<void>((_resolve, reject) => {
            rejectDismiss = reject;
          }),
      )
      .mockResolvedValueOnce(undefined);
    renderDialog({ mode: 'onboarding', onClose });
    await screen.findByDisplayValue(existingProfile.learner_profile);
    const later = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.later',
    });

    await act(async () => {
      fireEvent.click(later);
    });
    fireEvent.click(later);
    expect(onClose).toHaveBeenCalledTimes(1);
    await act(async () => {
      rejectDismiss(new Error('skip request failed'));
    });

    expect(await screen.findByText('skip request failed')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(later);
    });
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(onClose).toHaveBeenNthCalledWith(1, 'dismiss');
    expect(onClose).toHaveBeenNthCalledWith(2, 'dismiss');
  });

  test('confirms before dismissing a dirty introduction', async () => {
    const onClose = jest.fn();
    renderDialog({ onClose });
    fireEvent.change(
      await screen.findByDisplayValue(existingProfile.learner_profile),
      { target: { value: 'Unsaved changes' } },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    );
    expect(await screen.findByRole('alertdialog')).toHaveTextContent(
      'module.profileOnboarding.dialog.discardTitle',
    );
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.keepEditing',
      }),
    );
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    );
    await act(async () => {
      fireEvent.click(
        await screen.findByRole('button', {
          name: 'module.profileOnboarding.dialog.discard',
        }),
      );
    });
    expect(onClose).toHaveBeenCalledWith('dismiss');
  });

  test('ignores a stale load after the account scope changes', async () => {
    let resolveUserA: (value: typeof existingProfile) => void = () => undefined;
    mockGetLearnerProfile
      .mockImplementationOnce(
        () =>
          new Promise(resolve => {
            resolveUserA = resolve;
          }),
      )
      .mockResolvedValueOnce({
        ...existingProfile,
        learner_profile: 'User B introduction',
      });
    const onClose = jest.fn();
    const { rerender } = render(
      <LearnerProfileDialog
        open={true}
        mode='settings'
        draftStorageScope='user-a'
        onClose={onClose}
      />,
    );
    await waitFor(() => expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1));

    rerender(
      <LearnerProfileDialog
        open={true}
        mode='settings'
        draftStorageScope='user-b'
        onClose={onClose}
      />,
    );
    expect(
      await screen.findByDisplayValue('User B introduction'),
    ).toBeEnabled();
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(2);
    await act(async () => {
      resolveUserA(existingProfile);
    });

    expect(screen.getByRole('textbox')).toHaveValue('User B introduction');
    expect(
      screen.queryByDisplayValue(existingProfile.learner_profile),
    ).toBeNull();
  });

  test('preserves an unsaved draft when the interface language changes', async () => {
    const onClose = jest.fn();
    const { rerender } = render(
      <LearnerProfileDialog
        open={true}
        mode='settings'
        draftStorageScope='user-a'
        onClose={onClose}
      />,
    );
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );
    fireEvent.change(editor, {
      target: { value: 'Unsaved learner introduction' },
    });

    mockLanguage = 'fr-FR';
    mockT = (key, params) => translateKey(key, params);
    rerender(
      <LearnerProfileDialog
        open={true}
        mode='settings'
        draftStorageScope='user-a'
        onClose={onClose}
      />,
    );

    expect(screen.getByRole('textbox')).toHaveValue(
      'Unsaved learner introduction',
    );
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1);
  });

  test('does not notify or close when a save resolves after unmount', async () => {
    let resolveSave: (value: typeof existingProfile) => void = () => undefined;
    mockUpdateLearnerProfile.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveSave = resolve;
        }),
    );
    const onSaved = jest.fn();
    const onClose = jest.fn();
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    const { unmount } = renderDialog({ onClose, onSaved });
    fireEvent.change(
      await screen.findByDisplayValue(existingProfile.learner_profile),
      { target: { value: 'Late saved introduction' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledTimes(1),
    );
    unmount();

    await act(async () => {
      resolveSave({
        ...existingProfile,
        learner_profile: 'Late saved introduction',
      });
    });

    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(onProfileChanged).not.toHaveBeenCalled();
    expect(mockToast).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('does not toast or close when a refresh fails after unmount', async () => {
    let rejectRefresh: (reason: Error) => void = () => undefined;
    const onSaved = jest.fn(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectRefresh = reject;
        }),
    );
    const onClose = jest.fn();
    const { unmount } = renderDialog({ onClose, onSaved });
    fireEvent.change(
      await screen.findByDisplayValue(existingProfile.learner_profile),
      { target: { value: 'Saved before switching accounts' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));

    unmount();
    await act(async () => {
      rejectRefresh(new Error('late account refresh failed'));
    });

    expect(onClose).not.toHaveBeenCalled();
    expect(mockToast).not.toHaveBeenCalledWith({
      title: 'module.profileOnboarding.refreshPending',
    });
  });
});
