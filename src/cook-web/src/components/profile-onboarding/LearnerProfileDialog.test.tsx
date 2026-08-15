import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {
  getLearnerProfile,
  optimizeLearnerProfile,
  updateLearnerProfile,
} from '@/api/learnerProfile';
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
  optimizeLearnerProfile: jest.fn(),
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
const mockOptimizeLearnerProfile = optimizeLearnerProfile as jest.Mock;
const mockUpdateLearnerProfile = updateLearnerProfile as jest.Mock;

const existingProfile = {
  learner_profile: 'Existing learner introduction',
  learner_profile_updated_at: '2026-08-11T01:00:00Z',
  has_learner_profile: true,
  max_length: 1000,
  nickname: 'Alex',
  nickname_max_length: 64,
};

const clearedProfile = {
  learner_profile: '',
  learner_profile_updated_at: null,
  has_learner_profile: false,
  max_length: 1000,
  nickname: 'Alex',
  nickname_max_length: 64,
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
    mockOptimizeLearnerProfile.mockReset();
  });

  test('shows an explicit optional nickname without parsing it from the introduction', async () => {
    renderDialog({ mode: 'onboarding' });

    await screen.findByDisplayValue(existingProfile.learner_profile);
    expect(screen.getAllByRole('textbox')).toHaveLength(2);
    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
    ).toHaveValue('Alex');
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
    expect(zhProfile.dialog.description).toContain('表达偏好');
    expect(zhProfile.dialog.promptHeading).toBe('可以从这些方面开始');
    expect(zhProfile.dialog.chips.identity.label).toBe('我的背景');
    expect(zhProfile.dialog.chips.identity.hint).toBe('身份、行业、职业等');
    expect(zhProfile.dialog.chips.goals.label).toBe('我的近况');
    expect(zhProfile.dialog.chips.goals.hint).toBe('近期状态、目标和困惑');
    expect(zhProfile.dialog.chips.teaching.label).toBe('我喜欢的语言风格');
    expect(zhProfile.dialog.chips.teaching.hint).toBe(
      '偏好的语气、表达，及禁忌',
    );
    expect(zhProfile.dialog.settingsTitle).toBe('向 AI 老师介绍你自己');
    expect(zhProfile.dialog.nicknameLabel).toBe('希望 AI 老师怎么称呼你');
    expect(zhProfile.dialog.profileLabel).toBe('希望 AI 老师长期知道的事');
    expect(zhProfile.dialog.optimize).toBe('帮我优化');
    expect(zhProfile.dialog.optimizeEmptyHint).toContain('先写几句');
    expect(zhProfile.dialog.optimizeHint).not.toContain('可选');
    expect(zhProfile.dialog.optimizeHint).toContain('补充有用细节');
    expect(zhProfile.dialog.optimizeHint).toContain('不改变原意或新增事实');
    expect(zhProfile.dialog.description).toBe(
      '写下你的背景、目标和表达偏好，让 AI 老师在课程中更贴近你的情况。',
    );
    expect(zhProfile.dialog.reassurance).toContain('真人老师');
    expect(zhProfile.dialog.reassurance).toContain('以老师设定为准');
    expect(JSON.stringify(zhProfile.dialog)).not.toMatch(
      /节奏|结构|分步骤|多提问/,
    );

    expect(enProfile.dialog.description).toContain('AI teacher');
    expect(enProfile.dialog.description).toContain('language preferences');
    expect(enProfile.dialog.settingsTitle).toBe(
      'Introduce yourself to your AI teacher',
    );
    expect(enProfile.dialog.nicknameLabel).toContain('AI teacher');
    expect(enProfile.dialog.nicknameLabel).toContain('optional');
    expect(enProfile.dialog.promptHeading).toBe('Start with any of these');
    expect(enProfile.dialog.chips.identity.label).toBe('My background');
    expect(enProfile.dialog.chips.identity.hint).toContain('industry');
    expect(enProfile.dialog.chips.goals.label).toBe('My current situation');
    expect(enProfile.dialog.chips.goals.hint).toContain('Current situation');
    expect(enProfile.dialog.chips.teaching.label).toBe(
      'My preferred language style',
    );
    expect(enProfile.dialog.chips.teaching.hint).toContain('expression');
    expect(enProfile.dialog.profileLabel).toContain('remember about you');
    expect(enProfile.dialog.optimize).toBe('Improve with AI');
    expect(enProfile.dialog.optimizeEmptyHint).toContain('Write a few lines');
    expect(enProfile.dialog.optimizeHint).toContain('useful detail');
    expect(enProfile.dialog.optimizeHint).not.toMatch(/optional/i);
    expect(enProfile.dialog.optimizeHint).toContain(
      'without changing your meaning or inventing facts',
    );
    expect(enProfile.dialog.description).toContain('background, goals');
    expect(enProfile.dialog.reassurance).toContain('human teacher');
    expect(JSON.stringify(enProfile.dialog)).not.toMatch(
      /teaching pace|teaching structure|step by step|ask more questions/i,
    );

    expect(frProfile.dialog.description).toContain('enseignant IA');
    expect(frProfile.dialog.description).toContain('préférences de langage');
    expect(frProfile.dialog.settingsTitle).toBe(
      'Présentez-vous à votre enseignant IA',
    );
    expect(frProfile.dialog.nicknameLabel).toContain('enseignant IA');
    expect(frProfile.dialog.nicknameLabel).toContain('facultatif');
    expect(frProfile.dialog.promptHeading).toBe(
      'Commencez par l’un de ces aspects',
    );
    expect(frProfile.dialog.chips.identity.label).toBe('Mon parcours');
    expect(frProfile.dialog.chips.identity.hint).toContain('secteur');
    expect(frProfile.dialog.chips.goals.label).toBe('Ma situation actuelle');
    expect(frProfile.dialog.chips.goals.hint).toContain('Situation actuelle');
    expect(frProfile.dialog.chips.teaching.label).toBe(
      'Mon style de langage préféré',
    );
    expect(frProfile.dialog.chips.teaching.hint).toContain('expression');
    expect(frProfile.dialog.profileLabel).toContain('doit retenir de vous');
    expect(frProfile.dialog.optimize).toBe('Améliorer avec l’IA');
    expect(frProfile.dialog.optimizeEmptyHint).toContain(
      'Écrivez quelques lignes',
    );
    expect(frProfile.dialog.optimizeHint).toContain('détails utiles');
    expect(frProfile.dialog.optimizeHint).not.toMatch(/facultatif/i);
    expect(frProfile.dialog.optimizeHint).toContain(
      'sans changer votre intention',
    );
    expect(frProfile.dialog.description).toContain('vos objectifs');
    expect(frProfile.dialog.reassurance).toContain('enseignant humain');
    expect(JSON.stringify(frProfile.dialog)).not.toMatch(
      /rythme d’enseignement|structure d’enseignement|étape par étape|poser plus de questions/i,
    );
  });

  test('keeps the header concise and moves teacher course authority to the reassurance', async () => {
    renderDialog();

    await screen.findByDisplayValue(existingProfile.learner_profile);
    expect(
      screen.getByText('module.profileOnboarding.dialog.settingsDescription'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.description'),
    ).not.toBeInTheDocument();

    expect(zhProfile.dialog.settingsDescription).toBe(
      zhProfile.dialog.description,
    );
    expect(zhProfile.dialog.settingsDescription).not.toContain('真人老师');
    expect(zhProfile.dialog.reassurance).toContain('真人老师');
    expect(enProfile.dialog.settingsDescription).toBe(
      enProfile.dialog.description,
    );
    expect(enProfile.dialog.settingsDescription).not.toContain('human teacher');
    expect(enProfile.dialog.reassurance).toContain('human teacher');
    expect(frProfile.dialog.settingsDescription).toBe(
      frProfile.dialog.description,
    );
    expect(frProfile.dialog.settingsDescription).not.toContain(
      'enseignant humain',
    );
    expect(frProfile.dialog.reassurance).toContain('enseignant humain');
  });

  test('uses the approved concise cross-course placeholder in every language', () => {
    expect(zhProfile.dialog.profilePlaceholder).toBe(
      '例如：我在上海做办公室工作，大学学的是工商管理。最近想用 AI 把自己的想法做成文章和小工具。希望 AI 老师表达亲切直接、简洁易懂，少用术语。',
    );
    expect(enProfile.dialog.profilePlaceholder).toContain(
      'I work in an office in Shanghai',
    );
    expect(enProfile.dialog.profilePlaceholder).toContain(
      'turn my ideas into articles and small tools',
    );
    expect(enProfile.dialog.profilePlaceholder).toContain(
      'friendly, direct, concise, and easy to understand',
    );
    expect(frProfile.dialog.profilePlaceholder).toContain(
      'Je travaille dans un bureau à Shanghai',
    );
    expect(frProfile.dialog.profilePlaceholder).toContain(
      'transformer mes idées en articles et en petits outils',
    );
    expect(frProfile.dialog.profilePlaceholder).toContain(
      'chaleureuse, directe, concise et facile à comprendre',
    );
  });

  test('keeps a legacy nickname in its field while clearing prefilled profile text', async () => {
    mockT = (key, params) => {
      const value = String(params?.value || '');
      const legacyPrefill = {
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
    mockUpdateLearnerProfile.mockResolvedValue({
      ...clearedProfile,
      nickname: '小林',
    });
    const onSaved = jest.fn();
    const { props } = renderDialog({ mode: 'onboarding', onSaved });

    await waitFor(() => {
      expect(
        screen.getByLabelText('module.profileOnboarding.dialog.profileLabel'),
      ).toHaveValue('我的背景：办公室工作\n我喜欢的语言风格：亲切直接');
    });
    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
    ).toHaveValue('小林');
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveAndContinue',
    });
    expect(save).toBeEnabled();

    fireEvent.change(
      screen.getByLabelText('module.profileOnboarding.dialog.profileLabel'),
      { target: { value: '' } },
    );
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('');
      expect(props.onClose).toHaveBeenCalledWith('saved');
    });
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  test('migrates a displayed legacy nickname only when the new backend declares canonical state', async () => {
    const legacyFallbackResponse = {
      ...clearedProfile,
      nickname: '',
      legacy_profile_values: {
        sys_user_nickname: '小林',
      },
    };
    const canonicalResponse = {
      ...clearedProfile,
      nickname: '小林',
      legacy_profile_values: {},
    };
    mockGetLearnerProfile
      .mockResolvedValueOnce(legacyFallbackResponse)
      .mockResolvedValueOnce(canonicalResponse);
    mockUpdateLearnerProfile.mockResolvedValue(canonicalResponse);
    const onClose = jest.fn();
    const firstRender = renderDialog({ onClose });

    expect(await screen.findByDisplayValue('小林')).toBeEnabled();
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveChanges',
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('', '小林');
      expect(onClose).toHaveBeenCalledWith('saved');
    });
    firstRender.unmount();

    const reopenedClose = jest.fn();
    renderDialog({ onClose: reopenedClose });
    expect(await screen.findByDisplayValue('小林')).toBeEnabled();
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(2);
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    ).toBeDisabled();
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.dialog.cancel',
        }),
      );
    });
    expect(reopenedClose).toHaveBeenCalledWith('dismiss');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  test('does not treat a new-backend legacy nickname prefill as a discardable edit', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      ...clearedProfile,
      nickname: '',
      legacy_profile_values: {
        sys_user_nickname: '小林',
      },
    });
    const onClose = jest.fn();
    renderDialog({ onClose });

    expect(await screen.findByDisplayValue('小林')).toBeEnabled();
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.dialog.cancel',
        }),
      );
    });

    expect(onClose).toHaveBeenCalledWith('dismiss');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
  });

  test('shows but does not auto-migrate a legacy nickname from an older backend', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '',
      learner_profile_updated_at: null,
      has_learner_profile: false,
      max_length: 1000,
      legacy_profile_values: {
        sys_user_nickname: '小林',
      },
    });
    mockUpdateLearnerProfile.mockResolvedValue({
      learner_profile: 'New introduction',
      learner_profile_updated_at: null,
      has_learner_profile: true,
      max_length: 1000,
    });
    renderDialog();

    expect(await screen.findByDisplayValue('小林')).toBeEnabled();
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveChanges',
    });
    expect(save).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText('module.profileOnboarding.dialog.profileLabel'),
      { target: { value: 'New introduction' } },
    );
    fireEvent.click(save);

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('New introduction');
    });
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalledWith(
      'New introduction',
      '小林',
    );
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
    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
    ).toHaveValue('Alex');
    expect(screen.queryByDisplayValue('旧称呼')).not.toBeInTheDocument();
  });

  test('renders the aligned single-flow dialog with a prominent optimization action', async () => {
    renderDialog({ mode: 'onboarding' });

    await screen.findByDisplayValue(existingProfile.learner_profile);
    const dialog = screen.getByRole('dialog');
    const editor = screen.getByLabelText(
      'module.profileOnboarding.dialog.profileLabel',
    );
    const nicknameLabel = screen.getByText(
      'module.profileOnboarding.dialog.nicknameLabel',
    );
    const heading = screen.getByText(
      'module.profileOnboarding.dialog.onboardingTitle',
    );
    const description = screen.getByText(
      'module.profileOnboarding.dialog.description',
    );
    const promptHeading = screen.getByText(
      'module.profileOnboarding.dialog.promptHeading',
    );
    const identityPrompt = screen.getByTestId(
      'learner-profile-guidance-identity',
    );
    const optimizationCard = screen.getByTestId(
      'learner-profile-optimization-card',
    );
    const optimizationPanel = optimizationCard.firstElementChild;
    const reassurance = screen.getByTestId('learner-profile-reassurance');
    const mobileHandle = screen.getByTestId('learner-profile-mobile-handle');
    const later = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.later',
    });
    const primaryAction = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveAndContinue',
    });
    const footer = later.parentElement;
    const scrollContainer = Array.from(dialog.querySelectorAll('div')).find(
      element =>
        element.className.includes('min-h-0') &&
        element.className.includes('overflow-y-auto'),
    );
    const overlay = Array.from(
      document.body.querySelectorAll('[data-state="open"]'),
    ).find(element => element.className.includes('z-[100]'));

    expect(dialog).toHaveClass(
      'h-[calc(100dvh-96px)]',
      'sm:max-h-[min(97dvh,800px)]',
      'sm:max-w-[680px]',
      'sm:rounded-2xl',
    );
    expect(editor).toHaveClass(
      'h-[clamp(7rem,16dvh,11rem)]',
      'min-h-[clamp(7rem,16dvh,11rem)]',
      'max-h-[clamp(7rem,16dvh,11rem)]',
      'overflow-y-auto',
      'resize-none',
    );
    expect(editor).toHaveAttribute('rows', '4');
    expect(editor.style.height).toBe('');
    expect(editor.style.maxHeight).toBe('');
    expect(nicknameLabel).toHaveClass('font-semibold', 'text-foreground');
    const optimizeButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.optimize',
    });
    expect(optimizeButton).toHaveClass('min-h-11', 'shrink-0', 'shadow-sm');
    expect(optimizeButton).not.toHaveClass('w-full');
    expect(optimizationPanel).toHaveClass('h-24', 'sm:h-20');
    expect(identityPrompt).toHaveClass('min-h-16', 'rounded-xl', 'items-start');
    expect(identityPrompt).toHaveTextContent(
      'module.profileOnboarding.dialog.chips.identity.hint',
    );
    expect(optimizationCard).not.toHaveTextContent('29 / 1000');
    expect(screen.getByText('29 / 1000')).toBeInTheDocument();
    expect(optimizationCard).toHaveTextContent(
      'module.profileOnboarding.dialog.optimizeHint',
    );
    expect(
      optimizationCard.querySelectorAll('svg.lucide-sparkles'),
    ).toHaveLength(1);
    expect(heading.parentElement).toHaveClass(
      'w-full',
      'text-left',
      'sm:space-y-2',
    );
    expect(heading.parentElement).not.toHaveClass(
      'mx-auto',
      'max-w-[560px]',
      'text-center',
    );
    expect(heading.parentElement?.parentElement).toHaveClass('px-5', 'sm:px-8');
    expect(description).toHaveClass('text-left');
    expect(description).not.toHaveClass('sm:text-center');
    expect(scrollContainer).toHaveClass('overflow-y-auto', 'px-5', 'sm:px-8');
    expect(dialog.querySelector('svg.lucide-sparkles')).not.toBeNull();
    expect(mobileHandle).toHaveClass('sm:hidden');
    expect(
      screen.queryByTestId('learner-profile-writing-guide'),
    ).not.toBeInTheDocument();
    expect(
      promptHeading.compareDocumentPosition(identityPrompt) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      identityPrompt.compareDocumentPosition(editor) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      editor.compareDocumentPosition(optimizationCard) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(reassurance).toHaveTextContent(
      'module.profileOnboarding.dialog.reassurance',
    );
    expect(reassurance).toHaveClass('px-1', 'text-xs', 'sm:text-sm');
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

  test('keeps the optimization card visible but disabled until the learner writes a draft', async () => {
    mockGetLearnerProfile.mockResolvedValue(clearedProfile);
    renderDialog();

    const editor = await screen.findByLabelText(
      'module.profileOnboarding.dialog.profileLabel',
    );
    const optimize = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.optimize',
    });
    expect(optimize).toBeDisabled();
    expect(
      screen.getByText('module.profileOnboarding.dialog.optimizeEmptyHint'),
    ).toBeInTheDocument();
    fireEvent.change(editor, { target: { value: 'A few details about me' } });
    expect(optimize).toBeEnabled();
    expect(
      screen.getByText('module.profileOnboarding.dialog.optimizeHint'),
    ).toBeInTheDocument();
  });

  test('shows informative guidance cards without changing the draft', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      ...existingProfile,
      learner_profile: '',
      has_learner_profile: false,
    });
    renderDialog();
    const editor = await screen.findByLabelText(
      'module.profileOnboarding.dialog.profileLabel',
    );

    for (const prompt of ['identity', 'goals', 'teaching']) {
      const guidance = screen.getByTestId(`learner-profile-guidance-${prompt}`);
      expect(guidance.tagName).toBe('DIV');
      expect(guidance).toHaveTextContent(
        `module.profileOnboarding.dialog.chips.${prompt}.label`,
      );
      expect(guidance).toHaveTextContent(
        `module.profileOnboarding.dialog.chips.${prompt}.hint`,
      );
    }

    expect(editor).toHaveValue('');
    expect(
      screen
        .queryByTestId('learner-profile-guidance-identity')
        ?.closest('button'),
    ).toBeNull();
    expect(screen.getAllByRole('textbox')).toHaveLength(2);
  });

  test('optimizes the current draft in place and lets the user undo it', async () => {
    mockOptimizeLearnerProfile.mockResolvedValue({
      optimized_learner_profile: 'A clearer learner introduction',
    });
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    renderDialog();
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );

    expect(
      screen.getByTestId('learner-profile-optimization-card'),
    ).toHaveAttribute('aria-live', 'polite');
    expect(
      screen.getByTestId('learner-profile-optimization-card').firstElementChild,
    ).toHaveClass('h-24', 'sm:h-20');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );

    await waitFor(() => {
      expect(mockOptimizeLearnerProfile).toHaveBeenCalledWith(
        existingProfile.learner_profile,
      );
      expect(editor).toHaveValue('A clearer learner introduction');
    });
    expect(
      screen.getByText('module.profileOnboarding.dialog.optimizeSuccess'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('learner-profile-optimization-card').firstElementChild,
    ).toHaveClass('h-24', 'sm:h-20');
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();

    const undoButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.undoOptimize',
    });
    expect(undoButton).toHaveClass('min-h-11', 'sm:min-h-10');
    fireEvent.click(undoButton);
    expect(editor).toHaveValue(existingProfile.learner_profile);
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.dialog.undoOptimize',
      }),
    ).not.toBeInTheDocument();

    mockOptimizeLearnerProfile.mockResolvedValue({
      optimized_learner_profile: 'A clearer learner introduction',
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );
    await screen.findByDisplayValue('A clearer learner introduction');
    fireEvent.change(editor, {
      target: { value: 'My manually adjusted introduction' },
    });
    expect(editor).toHaveValue('My manually adjusted introduction');
    expect(
      screen.getByText('module.profileOnboarding.dialog.optimizeHint'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.dialog.undoOptimize',
      }),
    ).not.toBeInTheDocument();
    expect(onProfileChanged).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('locks only profile actions while optimization is pending and prevents duplicates', async () => {
    let resolveOptimization: (value: {
      optimized_learner_profile: string;
    }) => void = () => undefined;
    mockOptimizeLearnerProfile.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveOptimization = resolve;
        }),
    );
    renderDialog();
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );
    const nickname = screen.getByDisplayValue('Alex');
    const optimize = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.optimize',
    });

    fireEvent.click(optimize);

    expect(editor).toBeDisabled();
    expect(nickname).toBeEnabled();
    expect(
      screen.getByTestId('learner-profile-guidance-identity'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancel',
      }),
    ).toBeEnabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    ).toBeEnabled();
    const pendingOptimize = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.optimizing',
    });
    expect(pendingOptimize).toBeDisabled();
    fireEvent.click(pendingOptimize);
    expect(mockOptimizeLearnerProfile).toHaveBeenCalledTimes(1);

    fireEvent.change(nickname, { target: { value: 'Riley' } });
    await act(async () => {
      resolveOptimization({
        optimized_learner_profile: 'Optimized while nickname changes',
      });
    });
    expect(editor).toHaveValue('Optimized while nickname changes');
    expect(nickname).toHaveValue('Riley');
  });

  test('keeps the draft savable after a technical optimization failure', async () => {
    mockOptimizeLearnerProfile.mockRejectedValueOnce(
      Object.assign(new Error('AI optimization request timed out'), {
        code: 1025,
      }),
    );
    mockUpdateLearnerProfile.mockResolvedValue({
      ...existingProfile,
      learner_profile: 'My new draft',
    });
    renderDialog();
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );
    fireEvent.change(editor, { target: { value: 'My new draft' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );

    expect(
      await screen.findByText('AI optimization request timed out'),
    ).toBeInTheDocument();
    expect(editor).toHaveValue('My new draft');
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveChanges',
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('My new draft');
    });
  });

  test('shows the backend reason when profile moderation rejects optimization', async () => {
    mockOptimizeLearnerProfile.mockRejectedValueOnce(
      Object.assign(new Error('Revise the profile before optimizing it'), {
        code: 1022,
      }),
    );
    renderDialog();
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );

    expect(
      await screen.findByText('Revise the profile before optimizing it'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.optimizeFailed'),
    ).not.toBeInTheDocument();
    expect(editor).toHaveValue(existingProfile.learner_profile);
  });

  test('uses the model result exactly even when it only adds whitespace', async () => {
    mockOptimizeLearnerProfile.mockResolvedValue({
      optimized_learner_profile: `  ${existingProfile.learner_profile}  `,
    });
    renderDialog();
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );

    await screen.findByText('module.profileOnboarding.dialog.optimizeSuccess');
    expect(editor).toHaveValue(`  ${existingProfile.learner_profile}  `);
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.undoOptimize',
      }),
    ).toBeInTheDocument();
  });

  test('shows an over-limit model result instead of treating it as an optimization error', async () => {
    const optimized = 'x'.repeat(existingProfile.max_length + 1);
    mockOptimizeLearnerProfile.mockResolvedValue({
      optimized_learner_profile: optimized,
    });
    renderDialog();
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );

    await screen.findByText('module.profileOnboarding.dialog.optimizeSuccess');
    expect(editor).toHaveValue(optimized);
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    ).toBeDisabled();
  });

  test.each([
    [
      'missing field',
      {} as { optimized_learner_profile: string },
      'module.profileOnboarding.dialog.optimizeInvalidResponse',
    ],
    [
      'empty result',
      { optimized_learner_profile: '   ' },
      'module.profileOnboarding.dialog.optimizeEmptyResponse',
    ],
  ])(
    'reports a defensive frontend error for a %s response',
    async (_caseName, response, expectedMessage) => {
      mockOptimizeLearnerProfile.mockResolvedValueOnce(response);
      renderDialog();
      const editor = await screen.findByDisplayValue(
        existingProfile.learner_profile,
      );

      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.dialog.optimize',
        }),
      );

      expect(await screen.findByText(expectedMessage)).toBeInTheDocument();
      expect(editor).toHaveValue(existingProfile.learner_profile);
    },
  );

  test('does not apply a late optimization result after the account changes', async () => {
    let resolveOptimization: (value: {
      optimized_learner_profile: string;
    }) => void = () => undefined;
    mockOptimizeLearnerProfile.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveOptimization = resolve;
        }),
    );
    mockGetLearnerProfile
      .mockResolvedValueOnce(existingProfile)
      .mockResolvedValueOnce({
        ...existingProfile,
        learner_profile: 'User B introduction',
        nickname: 'Bee',
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
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );

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
    await act(async () => {
      resolveOptimization({
        optimized_learner_profile: 'Late optimized user A introduction',
      });
    });

    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.profileLabel'),
    ).toHaveValue('User B introduction');
    expect(
      screen.queryByDisplayValue('Late optimized user A introduction'),
    ).not.toBeInTheDocument();
  });

  test('does not apply a late optimization result after the dialog closes', async () => {
    let resolveOptimization: (value: {
      optimized_learner_profile: string;
    }) => void = () => undefined;
    mockOptimizeLearnerProfile.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveOptimization = resolve;
        }),
    );
    const onClose = jest.fn();
    const { rerender } = render(
      <LearnerProfileDialog
        open={true}
        mode='settings'
        draftStorageScope='user-a'
        onClose={onClose}
      />,
    );
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );

    rerender(
      <LearnerProfileDialog
        open={false}
        mode='settings'
        draftStorageScope='user-a'
        onClose={onClose}
      />,
    );
    await act(async () => {
      resolveOptimization({
        optimized_learner_profile: 'Late optimized closed introduction',
      });
    });
    rerender(
      <LearnerProfileDialog
        open={true}
        mode='settings'
        draftStorageScope='user-a'
        onClose={onClose}
      />,
    );

    expect(
      await screen.findByDisplayValue(existingProfile.learner_profile),
    ).toBeEnabled();
    expect(
      screen.queryByDisplayValue('Late optimized closed introduction'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('module.profileOnboarding.dialog.optimizeHint'),
    ).toBeInTheDocument();
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
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('sends a changed nickname with the unchanged introduction', async () => {
    mockUpdateLearnerProfile.mockResolvedValue({
      ...existingProfile,
      nickname: 'Riley',
    });
    const onClose = jest.fn();
    renderDialog({ onClose });
    const nickname = await screen.findByDisplayValue('Alex');
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveChanges',
    });

    expect(nickname).toHaveAttribute('maxlength', '64');
    expect(save).toBeDisabled();
    fireEvent.change(nickname, { target: { value: ' Riley ' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(
        existingProfile.learner_profile,
        'Riley',
      );
      expect(onClose).toHaveBeenCalledWith('saved');
    });
    expect(mockToast).not.toHaveBeenCalled();
  });

  test('sends an explicit empty nickname only after the user clears it', async () => {
    mockUpdateLearnerProfile.mockResolvedValue({
      ...existingProfile,
      nickname: '',
    });
    renderDialog();
    const nickname = await screen.findByDisplayValue('Alex');

    fireEvent.change(nickname, { target: { value: '' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(
        existingProfile.learner_profile,
        '',
      );
    });
  });

  test.each([
    ['updates', 'Updated introduction'],
    ['clears', ''],
  ])(
    '%s the introduction without resending a historical over-limit nickname',
    async (_action, nextProfile) => {
      const historicalNickname = 'n'.repeat(80);
      mockGetLearnerProfile.mockResolvedValue({
        ...existingProfile,
        nickname: historicalNickname,
        nickname_max_length: 64,
      });
      mockUpdateLearnerProfile.mockResolvedValue({
        ...existingProfile,
        learner_profile: nextProfile,
        nickname: historicalNickname,
        nickname_max_length: 64,
      });
      renderDialog();

      const nickname = await screen.findByDisplayValue(historicalNickname);
      const profile = screen.getByDisplayValue(existingProfile.learner_profile);
      const save = screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      });
      expect(nickname).toHaveAttribute('maxlength', '64');

      fireEvent.change(profile, { target: { value: nextProfile } });
      expect(save).toBeEnabled();
      fireEvent.click(save);

      await waitFor(() => {
        expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(nextProfile);
      });
      expect(mockUpdateLearnerProfile).not.toHaveBeenCalledWith(
        nextProfile,
        historicalNickname,
      );
    },
  );

  test('still blocks an actively changed nickname above the current limit', async () => {
    const historicalNickname = 'n'.repeat(80);
    mockGetLearnerProfile.mockResolvedValue({
      ...existingProfile,
      nickname: historicalNickname,
      nickname_max_length: 64,
    });
    renderDialog();
    const nickname = await screen.findByDisplayValue(historicalNickname);
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveChanges',
    });

    fireEvent.change(nickname, { target: { value: 'r'.repeat(65) } });

    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
  });

  test('disables both fields and prevents duplicate saves while pending', async () => {
    let resolveSave: (value: typeof existingProfile) => void = () => undefined;
    mockUpdateLearnerProfile.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveSave = resolve;
        }),
    );
    renderDialog();
    const nickname = await screen.findByDisplayValue('Alex');
    const profile = screen.getByDisplayValue(existingProfile.learner_profile);
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveChanges',
    });

    fireEvent.change(nickname, { target: { value: 'Riley' } });
    fireEvent.click(save);
    expect(nickname).toBeDisabled();
    expect(profile).toBeDisabled();
    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(mockUpdateLearnerProfile).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveSave({ ...existingProfile, nickname: 'Riley' });
    });
  });

  test('saves an empty introduction while preserving an unchanged nickname', async () => {
    const calls: string[] = [];
    const onClose = jest.fn((reason: 'dismiss' | 'saved') => {
      calls.push(`close:${reason}`);
    });
    const onSaved = jest.fn(() => {
      calls.push('saved');
    });
    const onProfileChanged = jest.fn(() => {
      calls.push('event');
    });
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    mockUpdateLearnerProfile.mockResolvedValue(clearedProfile);
    renderDialog({ onClose, onSaved });
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveChanges',
    });

    expect(save).toBeDisabled();
    fireEvent.change(editor, { target: { value: '' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('');
      expect(onClose).toHaveBeenCalledWith('saved');
    });
    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
    ).toHaveValue('Alex');
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onProfileChanged).toHaveBeenCalledTimes(1);
    expect(calls).toEqual(['event', 'saved', 'close:saved']);
    expect(mockToast).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('keeps the dialog open when saving an empty profile fails', async () => {
    mockUpdateLearnerProfile.mockRejectedValueOnce(
      new Error('clear request failed'),
    );
    const onSaved = jest.fn();
    const onClose = jest.fn();
    renderDialog({ onClose, onSaved });
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveChanges',
    });

    fireEvent.change(editor, { target: { value: '' } });
    fireEvent.click(save);

    expect(await screen.findByText('clear request failed')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(save).toBeEnabled();
    expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('');
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(mockToast).not.toHaveBeenCalled();
  });

  test('does not save when both canonical and legacy profile values load empty', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      ...clearedProfile,
      learner_profile_updated_at: null,
      nickname: '',
      legacy_profile_values: {},
    });
    renderDialog({ mode: 'onboarding' });
    const editor = screen.getByLabelText(
      'module.profileOnboarding.dialog.profileLabel',
    );
    await waitFor(() => expect(editor).toBeEnabled());
    const save = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.saveAndContinue',
    });

    expect(editor).toHaveValue('');
    expect(save).toBeDisabled();
    fireEvent.change(editor, { target: { value: '   ' } });
    expect(save).toBeDisabled();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
  });

  test('keeps the editor protected after load failure and retries', async () => {
    mockGetLearnerProfile
      .mockRejectedValueOnce(new Error('load request failed'))
      .mockResolvedValueOnce(existingProfile);
    renderDialog();

    expect(await screen.findByText('load request failed')).toBeInTheDocument();
    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.profileLabel'),
    ).toBeDisabled();
    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
    ).toBeDisabled();
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
        nickname: 'Bee',
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

    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.profileLabel'),
    ).toHaveValue('User B introduction');
    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
    ).toHaveValue('Bee');
    expect(
      screen.queryByDisplayValue(existingProfile.learner_profile),
    ).toBeNull();
  });

  test('does not apply profile or nickname save results after the account changes', async () => {
    let resolveClear: (value: typeof clearedProfile) => void = () => undefined;
    mockUpdateLearnerProfile.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveClear = resolve;
        }),
    );
    mockGetLearnerProfile
      .mockResolvedValueOnce(existingProfile)
      .mockResolvedValueOnce({
        ...existingProfile,
        learner_profile: 'User B introduction',
        nickname: 'Bee',
      });
    const onSaved = jest.fn();
    const onClose = jest.fn();
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    const { rerender } = render(
      <LearnerProfileDialog
        open={true}
        mode='settings'
        draftStorageScope='user-a'
        onClose={onClose}
        onSaved={onSaved}
      />,
    );
    const editor = await screen.findByDisplayValue(
      existingProfile.learner_profile,
    );
    fireEvent.change(editor, { target: { value: '' } });
    fireEvent.change(
      screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
      { target: { value: 'Account A nickname' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.saveChanges',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(
        '',
        'Account A nickname',
      ),
    );

    rerender(
      <LearnerProfileDialog
        open={true}
        mode='settings'
        draftStorageScope='user-b'
        onClose={onClose}
        onSaved={onSaved}
      />,
    );
    expect(
      await screen.findByDisplayValue('User B introduction'),
    ).toBeEnabled();
    await act(async () => {
      resolveClear(clearedProfile);
    });

    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.profileLabel'),
    ).toHaveValue('User B introduction');
    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
    ).toHaveValue('Bee');
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(onProfileChanged).not.toHaveBeenCalled();
    expect(mockToast).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
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

    expect(
      screen.getByLabelText('module.profileOnboarding.dialog.profileLabel'),
    ).toHaveValue('Unsaved learner introduction');
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
