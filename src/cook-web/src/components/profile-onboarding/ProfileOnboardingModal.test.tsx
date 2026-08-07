import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { createProfileOnboardingSession } from '@/c-api/user';
import ProfileOnboardingModal, {
  countUnicodeCodePoints,
  ProfileDraftEditor,
} from './ProfileOnboardingModal';

const EXTERNAL_PROMPT = [
  '只包括：',
  '称呼',
  '职业背景、身份与相关经验',
  '表达风格',
  '幻灯片风格',
  '最近关注的事情',
].join('\n');
const START_GUIDED_SESSION_LABEL = 'start guided session';
const FINISH_GUIDED_PROFILE_LABEL = 'finish guided profile';
const mockTrackEvent = jest.fn();
const mockScrollTo = jest.fn();
let latestOnDraftReady:
  | ((draft: string, sessionId: string) => void)
  | undefined;
const originalScrollToDescriptor = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  'scrollTo',
);
const LEGACY_PASTE_DRAFT_STORAGE_KEY =
  'profile-onboarding-paste-draft:profile-v2';
const ACTIVE_PASTE_DRAFT_STORAGE_KEY =
  'profile-onboarding-paste-draft:active-user:profile-v2';
const scopedDraftKey = (userId: string) =>
  `profile-onboarding-paste-draft:profile-v2:${encodeURIComponent(userId)}`;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      if (key === 'module.profileOnboarding.externalAgent.prompt') {
        return EXTERNAL_PROMPT;
      }
      if (
        key === 'module.profileOnboarding.characterCount' ||
        key === 'module.profileOnboarding.onboardingCharacterCount'
      ) {
        return `${params?.count} / ${params?.max}`;
      }
      if (
        key === 'module.profileOnboarding.characterCountOverLimit' ||
        key === 'module.profileOnboarding.onboardingCharacterCountOverLimit'
      ) {
        return `${params?.count} characters; limit ${params?.max}`;
      }
      return key;
    },
    i18n: { language: 'zh-CN', resolvedLanguage: 'zh-CN' },
  }),
}));

jest.mock('@/c-api/user', () => ({
  createProfileOnboardingSession: jest.fn(),
  runProfileOnboardingSession: jest.fn(),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('./ProfileOnboardingConversation', () => ({
  __esModule: true,
  default: ({
    onDraftReady,
    onSessionStarted,
    createSession,
    disabled,
  }: {
    onDraftReady: (draft: string, id: string) => void;
    onSessionStarted?: (id: string) => void;
    createSession: () => unknown;
    disabled?: boolean;
  }) => {
    latestOnDraftReady = onDraftReady;
    return (
      <div data-testid='mock-guided-conversation'>
        <button
          type='button'
          disabled={disabled}
          onClick={() => {
            void createSession();
            onSessionStarted?.('session-1');
          }}
        >
          {START_GUIDED_SESSION_LABEL}
        </button>
        <button
          type='button'
          disabled={disabled}
          onClick={() => onDraftReady('引导生成的画像', 'session-1')}
        >
          {FINISH_GUIDED_PROFILE_LABEL}
        </button>
      </div>
    );
  },
}));

const choosePasteRoute = () => {
  const routeButton = screen.getByRole('button', {
    name: /module.profileOnboarding.hasAgent.yes/,
  });
  fireEvent.click(routeButton);
  expect(routeButton).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.next',
    }),
  );
};

const chooseGuidedRoute = () => {
  const routeButton = screen.getByRole('button', {
    name: /module.profileOnboarding.hasAgent.no/,
  });
  fireEvent.click(routeButton);
  expect(routeButton).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.next',
    }),
  );
};

describe('ProfileOnboardingModal v2', () => {
  beforeEach(() => {
    latestOnDraftReady = undefined;
    jest.clearAllMocks();
    window.sessionStorage.clear();
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      configurable: true,
      value: mockScrollTo,
    });
    Object.assign(navigator, {
      clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
    if (originalScrollToDescriptor) {
      Object.defineProperty(
        HTMLElement.prototype,
        'scrollTo',
        originalScrollToDescriptor,
      );
    } else {
      Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo');
    }
  });

  test('keeps the shared settings editor on its auto-resizing default', () => {
    render(
      <ProfileDraftEditor
        value='现有设置'
        maxLength={1000}
        disabled={false}
        onChange={jest.fn()}
      />,
    );

    const editor = screen.getByRole('textbox');
    expect(editor).toHaveAttribute('rows', '8');
    expect(editor).not.toHaveClass('resize-none');
    expect(editor).not.toHaveClass('h-[184px]');
  });

  test('selects a familiar-agent route before continuing to it', () => {
    render(
      <ProfileOnboardingModal
        open
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    expect(
      screen.getByRole('heading', {
        name: 'module.profileOnboarding.choice.title',
      }),
    ).toBeInTheDocument();
    const privacySummaries = screen.getAllByText(
      'module.profileOnboarding.privacySummary',
    );
    expect(privacySummaries).toHaveLength(1);
    const [privacySummary] = privacySummaries;
    expect(
      screen.queryByText('module.profileOnboarding.sidebarDescription'),
    ).not.toBeInTheDocument();
    const familiarAgentButton = screen.getByRole('button', {
      name: /module.profileOnboarding.hasAgent.yes/,
    });
    expect(familiarAgentButton).toBeInTheDocument();
    expect(
      familiarAgentButton.compareDocumentPosition(privacySummary) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.no/,
      }),
    ).toBeInTheDocument();
    expect(familiarAgentButton).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(familiarAgentButton);

    expect(familiarAgentButton).toHaveAttribute('aria-pressed', 'true');
    expect(
      screen.queryByText((_, node) => node?.textContent === EXTERNAL_PROMPT),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );

    expect(
      screen.getByText((_, node) => node?.textContent === EXTERNAL_PROMPT),
    ).toBeInTheDocument();
  });

  test('keeps three footer slots in stable DOM order across every route', () => {
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    const footer = screen.getByTestId('profile-onboarding-footer');
    const backSlot = screen.getByTestId('profile-onboarding-footer-back');
    const secondarySlot = screen.getByTestId(
      'profile-onboarding-footer-secondary',
    );
    const primarySlot = screen.getByTestId('profile-onboarding-footer-primary');
    const expectStableFooter = () => {
      expect(Array.from(footer.children)).toEqual([
        backSlot,
        secondarySlot,
        primarySlot,
      ]);
      expect(footer).not.toHaveClass('flex-col-reverse');
      expect(screen.getByTestId('profile-onboarding-footer-back')).toBe(
        backSlot,
      );
      expect(screen.getByTestId('profile-onboarding-footer-secondary')).toBe(
        secondarySlot,
      );
      expect(screen.getByTestId('profile-onboarding-footer-primary')).toBe(
        primarySlot,
      );
    };

    expectStableFooter();
    choosePasteRoute();
    expectStableFooter();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '用于确认 footer 稳定的内容' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );
    expectStableFooter();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.back',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.back',
      }),
    );
    chooseGuidedRoute();
    expectStableFooter();
  });

  test('reviews pasted text before submitting and preserves it across a real back step', async () => {
    const now = jest.spyOn(Date, 'now').mockReturnValue(1_000);
    const onComplete = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        draftStorageScope='user-paste'
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );

    choosePasteRoute();
    expect(
      screen.getByText((_, node) => node?.textContent === EXTERNAL_PROMPT),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.externalAgent.switchHint'),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.externalAgent.copy',
      }),
    );
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        EXTERNAL_PROMPT,
      );
    });

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '我是一名产品经理，喜欢简洁的解释。' },
    });
    expect(window.sessionStorage.getItem(scopedDraftKey('user-paste'))).toBe(
      '我是一名产品经理，喜欢简洁的解释。',
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );

    expect(onComplete).not.toHaveBeenCalled();
    expect(
      screen.getByRole('heading', {
        name: 'module.profileOnboarding.review.title',
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveValue(
      '我是一名产品经理，喜欢简洁的解释。',
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.back',
      }),
    );

    expect(
      screen.getByRole('heading', {
        name: 'module.profileOnboarding.externalAgent.title',
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveValue(
      '我是一名产品经理，喜欢简洁的解释。',
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );

    now.mockReturnValue(2_750);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(
        '我是一名产品经理，喜欢简洁的解释。',
        'pasted',
        undefined,
      );
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'profile_onboarding_completed',
        {
          source: 'pasted',
          presentation: 'blocking',
          duration_ms: 1_750,
        },
      );
    });
    expect(
      window.sessionStorage.getItem(scopedDraftKey('user-paste')),
    ).toBeNull();
  });

  test('keeps the pasted draft when saving fails', async () => {
    const onComplete = jest.fn().mockResolvedValue(false);
    render(
      <ProfileOnboardingModal
        open
        draftStorageScope='user-failed-save'
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );
    choosePasteRoute();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '保留这个草稿' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );
    expect(onComplete).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(
      window.sessionStorage.getItem(scopedDraftKey('user-failed-save')),
    ).toBe('保留这个草稿');
  });

  test('keeps confirmation single-flight and blocks every exit while it is pending', async () => {
    let resolveComplete: ((value: boolean) => void) | undefined;
    const completion = new Promise<boolean>(resolve => {
      resolveComplete = resolve;
    });
    const onComplete = jest.fn(() => completion);
    const onSkip = jest.fn();
    render(
      <ProfileOnboardingModal
        open
        onComplete={onComplete}
        onSkip={onSkip}
      />,
    );

    choosePasteRoute();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '等待保存的内容' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );
    const confirmButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.complete',
    });
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const backButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.back',
    });
    const skipButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.skip',
    });
    expect(confirmButton).toBeDisabled();
    expect(backButton).toBeDisabled();
    expect(skipButton).toBeDisabled();

    fireEvent.click(backButton);
    fireEvent.click(skipButton);
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.pointerDown(document.body);

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onSkip).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await act(async () => {
      resolveComplete?.(false);
      await completion;
    });
    await waitFor(() => {
      expect(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.complete',
        }),
      ).toBeEnabled();
    });
  });

  test('locks the guided conversation and ignores late results while skipping', async () => {
    let resolveSkip: ((value: boolean) => void) | undefined;
    const skip = new Promise<boolean>(resolve => {
      resolveSkip = resolve;
    });
    const onSkip = jest.fn(() => skip);
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={jest.fn()}
        onSkip={onSkip}
      />,
    );

    chooseGuidedRoute();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.skip',
      }),
    );

    await waitFor(() => expect(onSkip).toHaveBeenCalledTimes(1));
    expect(
      screen.getByRole('button', { name: START_GUIDED_SESSION_LABEL }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', { name: FINISH_GUIDED_PROFILE_LABEL }),
    ).toBeDisabled();

    act(() => {
      latestOnDraftReady?.('不应采用的迟到结果', 'session-late');
    });
    expect(screen.queryByDisplayValue('不应采用的迟到结果')).toBeNull();
    expect(
      screen.getByText('module.profileOnboarding.guided.title'),
    ).toBeInTheDocument();

    await act(async () => {
      resolveSkip?.(false);
      await skip;
    });
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: START_GUIDED_SESSION_LABEL }),
      ).toBeEnabled();
    });
  });

  test('allows skipping only through the explicit skip button', async () => {
    const now = jest.spyOn(Date, 'now').mockReturnValue(4_000);
    const onSkip = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        presentation='non_blocking'
        onComplete={jest.fn()}
        onSkip={onSkip}
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'component.header.close' }),
    ).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.pointerDown(document.body);
    expect(onSkip).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    now.mockReturnValue(4_640);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.skip',
      }),
    );

    await waitFor(() => {
      expect(onSkip).toHaveBeenCalledWith(undefined);
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'profile_onboarding_skipped',
        {
          action: 'skipped',
          presentation: 'non_blocking',
          duration_ms: 640,
        },
      );
    });
  });

  test('focuses each route heading and resets page scroll on forward and back navigation', async () => {
    render(
      <ProfileOnboardingModal
        open
        presentation='non_blocking'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    const choiceHeading = screen.getByRole('heading', {
      name: 'module.profileOnboarding.choice.title',
    });
    await waitFor(() => expect(choiceHeading).toHaveFocus());
    expect(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    ).not.toHaveFocus();

    const choiceBody = screen.getByTestId('profile-onboarding-body');
    choiceBody.scrollTop = 240;
    mockScrollTo.mockClear();
    choosePasteRoute();

    const pasteHeading = screen.getByRole('heading', {
      name: 'module.profileOnboarding.externalAgent.title',
    });
    await waitFor(() => expect(pasteHeading).toHaveFocus());
    expect(screen.getByTestId('profile-onboarding-body')).toHaveProperty(
      'scrollTop',
      0,
    );
    expect(mockScrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'auto' });

    const pasteBody = screen.getByTestId('profile-onboarding-body');
    pasteBody.scrollTop = 180;
    mockScrollTo.mockClear();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.back',
      }),
    );

    await waitFor(() => expect(choiceHeading).toHaveFocus());
    expect(screen.getByTestId('profile-onboarding-body')).toHaveProperty(
      'scrollTop',
      0,
    );
    expect(mockScrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'auto' });
  });

  test('keeps the modal and pasted draft when explicit skipping fails', async () => {
    const onSkip = jest.fn().mockResolvedValue(false);
    render(
      <ProfileOnboardingModal
        open
        presentation='non_blocking'
        draftStorageScope='user-failed-skip'
        onComplete={jest.fn()}
        onSkip={onSkip}
      />,
    );

    choosePasteRoute();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '保留这份草稿' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.skip',
      }),
    );

    await waitFor(() => expect(onSkip).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(
      window.sessionStorage.getItem(scopedDraftKey('user-failed-skip')),
    ).toBe('保留这份草稿');
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'profile_onboarding_skipped',
      expect.anything(),
    );
  });

  test('reviews guided output and returns to the same guided conversation before saving', async () => {
    const onComplete = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );
    chooseGuidedRoute();
    const guidedConversation = screen.getByTestId('mock-guided-conversation');
    fireEvent.click(
      screen.getByRole('button', { name: FINISH_GUIDED_PROFILE_LABEL }),
    );
    expect(screen.getByDisplayValue('引导生成的画像')).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.back',
      }),
    );
    expect(screen.getByTestId('mock-guided-conversation')).toBe(
      guidedConversation,
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );
    expect(screen.getByDisplayValue('引导生成的画像')).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );
    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(
        '引导生成的画像',
        'guided',
        'session-1',
      );
    });
  });

  test('restores the pasted draft after completing and leaving the guided route', () => {
    window.sessionStorage.setItem(
      scopedDraftKey('user-switches-routes'),
      '原来的粘贴草稿',
    );
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        draftStorageScope='user-switches-routes'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    chooseGuidedRoute();
    fireEvent.click(
      screen.getByRole('button', { name: FINISH_GUIDED_PROFILE_LABEL }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );
    choosePasteRoute();

    expect(screen.getByRole('textbox')).toHaveValue('原来的粘贴草稿');
    expect(
      window.sessionStorage.getItem(scopedDraftKey('user-switches-routes')),
    ).toBe('原来的粘贴草稿');
  });

  test('ignores a late guided result after the learner switches to pasted input', () => {
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    chooseGuidedRoute();
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
    fireEvent.click(screen.getByText(FINISH_GUIDED_PROFILE_LABEL));
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );

    expect(screen.getByRole('textbox')).toHaveValue('');
    expect(
      screen.getByText('module.profileOnboarding.externalAgent.title'),
    ).toBeInTheDocument();
  });

  test('uses onboarding intent for the default guided route', () => {
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    chooseGuidedRoute();
    fireEvent.click(
      screen.getByRole('button', { name: START_GUIDED_SESSION_LABEL }),
    );

    expect(createProfileOnboardingSession).toHaveBeenCalledWith(
      'zh-CN',
      'onboarding',
    );
  });

  test('passes settings intent to a voluntary guided rerun', () => {
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        sessionIntent='settings'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.cancel',
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.skip',
      }),
    ).not.toBeInTheDocument();

    choosePasteRoute();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '设置页更新后的背景和偏好' },
    });
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );

    chooseGuidedRoute();
    fireEvent.click(
      screen.getByRole('button', { name: START_GUIDED_SESSION_LABEL }),
    );

    expect(createProfileOnboardingSession).toHaveBeenCalledWith(
      'zh-CN',
      'settings',
    );
  });

  test('keeps oversized pasted text intact and disables saving until it is shortened', () => {
    const oversizedDraft = 'A😀你X';
    window.sessionStorage.setItem(
      scopedDraftKey('user-oversized'),
      oversizedDraft,
    );
    window.sessionStorage.setItem(
      ACTIVE_PASTE_DRAFT_STORAGE_KEY,
      scopedDraftKey('user-oversized'),
    );

    render(
      <ProfileOnboardingModal
        open
        draftStorageScope='user-oversized'
        maxLength={3}
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );
    choosePasteRoute();

    expect(screen.getByRole('textbox')).toHaveValue(oversizedDraft);
    expect(screen.getByText('4 characters; limit 3')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    ).toBeDisabled();
    expect(
      window.sessionStorage.getItem(scopedDraftKey('user-oversized')),
    ).toBe(oversizedDraft);
  });

  test('validates the trimmed pasted profile length before review and submit', async () => {
    const onComplete = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        maxLength={3}
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );
    choosePasteRoute();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '  A😀你  ' },
    });

    expect(screen.getByText('3 / 3')).toBeInTheDocument();
    const nextButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.next',
    });
    expect(nextButton).toBeEnabled();
    fireEvent.click(nextButton);
    expect(onComplete).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith('A😀你', 'pasted', undefined);
    });
  });

  test('never submits a pasted profile with an abandoned guided session id', async () => {
    const onComplete = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );

    chooseGuidedRoute();
    fireEvent.click(
      screen.getByRole('button', { name: START_GUIDED_SESSION_LABEL }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );
    choosePasteRoute();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '改用已有智能体整理的画像' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.next',
      }),
    );
    expect(onComplete).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(
        '改用已有智能体整理的画像',
        'pasted',
        undefined,
      );
    });
  });

  test('restores a pasted draft only for the same user', () => {
    const firstRender = render(
      <ProfileOnboardingModal
        open
        draftStorageScope='user-same'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );
    choosePasteRoute();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '同一用户应恢复的草稿' },
    });
    expect(window.sessionStorage.getItem(scopedDraftKey('user-same'))).toBe(
      '同一用户应恢复的草稿',
    );

    firstRender.unmount();
    render(
      <ProfileOnboardingModal
        open
        draftStorageScope='user-same'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );
    choosePasteRoute();

    expect(screen.getByRole('textbox')).toHaveValue('同一用户应恢复的草稿');
  });

  test('does not expose a pasted draft after the active user changes', () => {
    const setItem = jest.spyOn(Storage.prototype, 'setItem');
    window.sessionStorage.setItem(
      LEGACY_PASTE_DRAFT_STORAGE_KEY,
      '旧版未隔离草稿',
    );
    const { rerender } = render(
      <ProfileOnboardingModal
        open
        draftStorageScope='user-a'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );
    choosePasteRoute();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '只属于用户 A 的草稿' },
    });
    expect(window.sessionStorage.getItem(scopedDraftKey('user-a'))).toBe(
      '只属于用户 A 的草稿',
    );

    rerender(
      <ProfileOnboardingModal
        open
        draftStorageScope='user-b'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );
    choosePasteRoute();

    expect(screen.getByRole('textbox')).toHaveValue('');
    expect(window.sessionStorage.getItem(scopedDraftKey('user-a'))).toBeNull();
    expect(setItem).not.toHaveBeenCalledWith(
      scopedDraftKey('user-b'),
      '只属于用户 A 的草稿',
    );
    expect(window.sessionStorage.getItem(scopedDraftKey('user-b'))).toBeNull();
    expect(
      window.sessionStorage.getItem(LEGACY_PASTE_DRAFT_STORAGE_KEY),
    ).toBeNull();
  });

  test('clears the previous user and legacy drafts when ownership changes closed', () => {
    window.sessionStorage.setItem(
      scopedDraftKey('user-a'),
      '只属于已退出用户的草稿',
    );
    window.sessionStorage.setItem(
      ACTIVE_PASTE_DRAFT_STORAGE_KEY,
      scopedDraftKey('user-a'),
    );
    window.sessionStorage.setItem(
      LEGACY_PASTE_DRAFT_STORAGE_KEY,
      '旧版未隔离草稿',
    );

    render(
      <ProfileOnboardingModal
        open={false}
        draftStorageScope='user-b'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    expect(window.sessionStorage.getItem(scopedDraftKey('user-a'))).toBeNull();
    expect(
      window.sessionStorage.getItem(LEGACY_PASTE_DRAFT_STORAGE_KEY),
    ).toBeNull();
    expect(window.sessionStorage.getItem(ACTIVE_PASTE_DRAFT_STORAGE_KEY)).toBe(
      scopedDraftKey('user-b'),
    );
  });

  test('counts Unicode code points instead of UTF-16 units', () => {
    expect(countUnicodeCodePoints('A😀你')).toBe(3);
  });
});
