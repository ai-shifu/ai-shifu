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
    expect(
      screen.getByText('module.profileOnboarding.dialog.description'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.settingsDescription'),
    ).not.toBeInTheDocument();

    expect(zhProfile.dialog.onboardingTitle).toContain('AI 老师');
    expect(zhProfile.dialog.description).toContain('AI 老师');
    expect(zhProfile.dialog.description).toContain('喜欢的语言风格');
    expect(zhProfile.dialog.promptHeading).toBe('可以从这三方面写起');
    expect(zhProfile.dialog.writingGuideTitle).toBe('可以包括');
    expect(zhProfile.dialog.chips.identity.label).toBe('我的情况');
    expect(zhProfile.dialog.chips.goals.label).toBe('我最近在意什么');
    expect(zhProfile.dialog.chips.teaching.label).toBe('我喜欢的语言风格');
    expect(zhProfile.dialog.chips.teaching.text).toContain('AI 老师');
    expect(zhProfile.dialog.chips.teaching.text).toContain('语言风格');
    expect(zhProfile.dialog.writingGuideTeaching).toContain('语言风格');
    expect(zhProfile.dialog.writingGuideTeaching).toContain('希望避免的表达');
    expect(zhProfile.dialog.profileLabel).toContain('长期了解');
    expect(zhProfile.dialog.description).not.toContain('课程');
    expect(JSON.stringify(zhProfile.dialog)).not.toMatch(
      /节奏|结构|分步骤|多提问/,
    );

    expect(enProfile.dialog.description).toContain('AI teacher');
    expect(enProfile.dialog.description).toContain('language style');
    expect(enProfile.dialog.promptHeading).toBe('Start with these three areas');
    expect(enProfile.dialog.writingGuideTitle).toBe('You can include');
    expect(enProfile.dialog.chips.identity.label).toBe('About me');
    expect(enProfile.dialog.chips.goals.label).toBe('What matters to me now');
    expect(enProfile.dialog.chips.teaching.label).toBe(
      'My preferred language style',
    );
    expect(enProfile.dialog.chips.teaching.text).toContain('AI teacher');
    expect(enProfile.dialog.chips.teaching.text).toContain('language style');
    expect(enProfile.dialog.writingGuideTeaching).toContain('language style');
    expect(enProfile.dialog.writingGuideTeaching).toContain(
      'wording you want to avoid',
    );
    expect(enProfile.dialog.profileLabel).toContain('remember about you');
    expect(enProfile.dialog.description).not.toMatch(/\bcourses?\b/i);
    expect(JSON.stringify(enProfile.dialog)).not.toMatch(
      /teaching pace|teaching structure|step by step|ask more questions/i,
    );

    expect(frProfile.dialog.description).toContain('enseignant IA');
    expect(frProfile.dialog.description).toContain('style de langage');
    expect(frProfile.dialog.promptHeading).toBe(
      'Commencez par ces trois aspects',
    );
    expect(frProfile.dialog.writingGuideTitle).toBe('Vous pouvez inclure');
    expect(frProfile.dialog.chips.identity.label).toBe('Ma situation');
    expect(frProfile.dialog.chips.goals.label).toBe(
      'Ce qui compte pour moi aujourd’hui',
    );
    expect(frProfile.dialog.chips.teaching.label).toBe(
      'Mon style de langage préféré',
    );
    expect(frProfile.dialog.chips.teaching.text).toContain('enseignant IA');
    expect(frProfile.dialog.chips.teaching.text).toContain('style de langage');
    expect(frProfile.dialog.writingGuideTeaching).toContain('style de langage');
    expect(frProfile.dialog.writingGuideTeaching).toContain(
      'formulations à éviter',
    );
    expect(frProfile.dialog.profileLabel).toContain('doit retenir de vous');
    expect(frProfile.dialog.description).not.toMatch(/\bcours\b/i);
    expect(JSON.stringify(frProfile.dialog)).not.toMatch(
      /rythme d’enseignement|structure d’enseignement|étape par étape|poser plus de questions/i,
    );
  });

  test('explains teacher course authority only in settings mode', async () => {
    renderDialog();

    await screen.findByDisplayValue(existingProfile.learner_profile);
    expect(
      screen.getByText('module.profileOnboarding.dialog.settingsDescription'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.description'),
    ).not.toBeInTheDocument();

    expect(zhProfile.dialog.settingsDescription).toContain(
      '真人老师为课程做出的设定',
    );
    expect(zhProfile.dialog.settingsDescription).toContain(
      '以真人老师的设定为准',
    );
    expect(enProfile.dialog.settingsDescription).toContain(
      'course design set by the human teacher',
    );
    expect(enProfile.dialog.settingsDescription).toContain(
      "follow the human teacher's design",
    );
    expect(frProfile.dialog.settingsDescription).toContain(
      'cadre défini pour le cours par l’enseignant humain',
    );
    expect(frProfile.dialog.settingsDescription).toContain('suivra ce cadre');
  });

  test('uses the approved relatable cross-course placeholder in every language', () => {
    const zhPlaceholder = zhProfile.dialog.profilePlaceholder;
    const enPlaceholder = enProfile.dialog.profilePlaceholder;
    const frPlaceholder = frProfile.dialog.profilePlaceholder;

    for (const detail of [
      '可以叫我',
      '住在上海',
      '大学学工商管理',
      '普通的办公室工作',
      '整理资料、写邮件、做表格',
      '没有技术背景',
      '下班后的时间也不多',
      '属于自己的事',
      '借助 AI 整理想法、补足知识',
      '城市生活和职场的观察',
      '文章和小工具',
      '长期投入的个人事业',
      '术语和复杂表述',
      '语言风格亲切直接、口语化、简洁',
      '不要太正式',
      '少用不必要的术语',
    ]) {
      expect(zhPlaceholder).toContain(detail);
    }
    for (const courseSpecificDetail of [
      'Excel',
      '数据分析',
      '月度报告',
      '销售额',
      '产品经理',
      'AI 产品',
      '分步骤',
      '讲解结构',
      '多提问',
    ]) {
      expect(zhPlaceholder).not.toContain(courseSpecificDetail);
    }

    for (const detail of [
      'call me',
      'live in Shanghai',
      'studied business administration',
      'regular office job',
      'organizing documents, writing emails, and making spreadsheets',
      'do not have a technical background',
      'limited time after work',
      'something of my own',
      'use AI to organize my ideas and fill gaps in my knowledge',
      'observations about city life and work',
      'useful articles and small tools',
      'personal project I can pursue for years',
      'terminology and complicated wording',
      'friendly, direct, conversational, and concise language style',
      'not too formal',
      'avoids unnecessary jargon',
    ]) {
      expect(enPlaceholder).toContain(detail);
    }
    for (const courseSpecificDetail of [
      'Excel',
      'data analysis',
      'monthly report',
      'sales revenue',
      'AI products',
      'step by step',
      'teaching structure',
      'ask more questions',
    ]) {
      expect(enPlaceholder).not.toContain(courseSpecificDetail);
    }

    for (const detail of [
      'm’appeler',
      'vis à Shanghai',
      'étudié la gestion à l’université',
      'emploi de bureau ordinaire',
      'classe des documents, écris des e-mails et prépare des tableaux',
      'pas de formation technique',
      'peu de temps après le travail',
      'projet qui m’appartienne',
      'utiliser l’IA pour organiser mes idées et compléter mes connaissances',
      'observations sur la vie en ville et le travail',
      'articles et petits outils utiles',
      'projet personnel durable',
      'termes nouveaux et les formulations complexes',
      'style chaleureux, direct, simple et concis',
      'sans être trop formel',
      'jargon inutile',
    ]) {
      expect(frPlaceholder).toContain(detail);
    }
    for (const courseSpecificDetail of [
      'Excel',
      'analyse de données',
      'rapport mensuel',
      'chiffre d’affaires',
      'produits IA',
      'étape par étape',
      'structure d’enseignement',
      'poser plus de questions',
    ]) {
      expect(frPlaceholder).not.toContain(courseSpecificDetail);
    }
  });

  test('prefills an empty canonical profile from legacy system variables', async () => {
    mockT = (key, params) => {
      const value = String(params?.value || '');
      const legacyPrefill = {
        'module.profileOnboarding.dialog.legacyPrefill.nickname': `可以叫我 ${value}。`,
        'module.profileOnboarding.dialog.legacyPrefill.background': `我的背景：${value}`,
        'module.profileOnboarding.dialog.legacyPrefill.style': `我喜欢的语言风格：${value}`,
      };
      return legacyPrefill[key as keyof typeof legacyPrefill] ?? key;
    };
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '',
      learner_profile_updated_at: null,
      has_learner_profile: false,
      max_length: 1000,
      legacy_profile_values: {
        sys_user_nickname: '小林',
        sys_user_background: '办公室工作',
        sys_user_style: '亲切直接',
      },
    });
    const { props } = renderDialog();

    await waitFor(() => {
      expect(screen.getByRole('textbox')).toHaveValue(
        '可以叫我 小林。\n我的背景：办公室工作\n我喜欢的语言风格：亲切直接',
      );
    });
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    ).toBeEnabled();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancel',
      }),
    );
    await waitFor(() => {
      expect(props.onClose).toHaveBeenCalledWith('dismiss');
    });
    expect(
      screen.queryByText('module.profileOnboarding.dialog.discardTitle'),
    ).not.toBeInTheDocument();
  });

  test('keeps an existing canonical profile instead of legacy values', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      ...existingProfile,
      legacy_profile_values: {
        sys_user_nickname: '旧称呼',
        sys_user_background: '旧背景',
        sys_user_style: '旧风格',
      },
    });

    renderDialog();

    await screen.findByDisplayValue(existingProfile.learner_profile);
    expect(screen.queryByDisplayValue(/旧背景/)).not.toBeInTheDocument();
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
    expect(editor).toHaveClass('min-h-[215px]', 'sm:min-h-[168px]');
    expect(heading.parentElement).toHaveClass('sm:space-y-2');
    expect(writingGuide).toHaveClass('sm:py-3');
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
    expect(later).toHaveClass('flex-1', 'sm:flex-none');
    expect(primaryAction).toHaveClass('flex-[1.4]', 'sm:flex-none');
    expect(later).not.toHaveClass('sm:min-w-40');
    expect(primaryAction).not.toHaveClass('sm:min-w-80');
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
    expect(mockToast).not.toHaveBeenCalled();
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

  test('does not toast or close when a save rejects after unmount', async () => {
    let rejectSave: (reason: Error) => void = () => undefined;
    mockUpdateLearnerProfile.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectSave = reject;
        }),
    );
    const onSaved = jest.fn();
    const onClose = jest.fn();
    const { unmount } = renderDialog({ onClose, onSaved });
    fireEvent.change(
      await screen.findByDisplayValue(existingProfile.learner_profile),
      { target: { value: 'Late rejected introduction' } },
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
      rejectSave(new Error('late save failed'));
    });

    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(mockToast).not.toHaveBeenCalled();
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

  test('keeps refresh failure feedback after a successful save', async () => {
    const onSaved = jest.fn().mockRejectedValue(new Error('refresh failed'));
    const onClose = jest.fn();
    renderDialog({ onClose, onSaved });

    fireEvent.change(
      await screen.findByDisplayValue(existingProfile.learner_profile),
      { target: { value: 'Saved while refresh fails' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'module.profileOnboarding.refreshPending',
      });
      expect(onClose).toHaveBeenCalledWith('saved');
    });
  });
});
