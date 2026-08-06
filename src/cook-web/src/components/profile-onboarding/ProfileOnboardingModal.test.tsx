import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createProfileOnboardingSession } from '@/c-api/user';
import ProfileOnboardingModal, {
  countUnicodeCodePoints,
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
      if (key === 'module.profileOnboarding.characterCount') {
        return `${params?.count} / ${params?.max}`;
      }
      if (key === 'module.profileOnboarding.characterCountOverLimit') {
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
  }: {
    onDraftReady: (draft: string, id: string) => void;
    onSessionStarted?: (id: string) => void;
    createSession: () => unknown;
  }) => (
    <>
      <button
        type='button'
        onClick={() => {
          void createSession();
          onSessionStarted?.('session-1');
        }}
      >
        {START_GUIDED_SESSION_LABEL}
      </button>
      <button
        type='button'
        onClick={() => onDraftReady('引导生成的画像', 'session-1')}
      >
        {FINISH_GUIDED_PROFILE_LABEL}
      </button>
    </>
  ),
}));

describe('ProfileOnboardingModal v2', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.sessionStorage.clear();
    Object.assign(navigator, {
      clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('asks about a familiar agent before choosing a path', () => {
    render(
      <ProfileOnboardingModal
        open
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    expect(
      screen.getByText('module.profileOnboarding.routeQuestion'),
    ).toBeInTheDocument();
    const privacyNotice = screen.getByText(
      'module.profileOnboarding.privacyNotice',
    );
    const familiarAgentButton = screen.getByRole('button', {
      name: /module.profileOnboarding.hasAgent.yes/,
    });
    expect(familiarAgentButton).toBeInTheDocument();
    expect(
      privacyNotice.compareDocumentPosition(familiarAgentButton) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.no/,
      }),
    ).toBeInTheDocument();
  });

  test('copies the five-area external-agent prompt and submits pasted text', async () => {
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

    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
    expect(
      screen.getByText((_, node) => node?.textContent === EXTERNAL_PROMPT),
    ).toBeInTheDocument();

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
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '保留这个草稿' },
    });
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

  test('allows skipping only through the explicit maybe-later button', async () => {
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

  test('focuses the heading instead of making the first route look selected', async () => {
    render(
      <ProfileOnboardingModal
        open
        presentation='non_blocking'
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    const heading = screen.getByRole('heading', {
      name: 'module.profileOnboarding.title',
    });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    ).not.toHaveFocus();
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

    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
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

  test('reviews guided runtime output before saving it', async () => {
    const onComplete = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.no/,
      }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: FINISH_GUIDED_PROFILE_LABEL }),
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

  test('uses onboarding intent for the default guided route', () => {
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.no/,
      }),
    );
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

    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.no/,
      }),
    );
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
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );

    expect(screen.getByRole('textbox')).toHaveValue(oversizedDraft);
    expect(screen.getByText('4 characters; limit 3')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    ).toBeDisabled();
    expect(
      window.sessionStorage.getItem(scopedDraftKey('user-oversized')),
    ).toBe(oversizedDraft);
  });

  test('validates and submits the trimmed pasted profile length', async () => {
    const onComplete = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        maxLength={3}
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '  A😀你  ' },
    });

    expect(screen.getByText('3 / 3')).toBeInTheDocument();
    const completeButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.complete',
    });
    expect(completeButton).toBeEnabled();
    fireEvent.click(completeButton);

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith('A😀你', 'pasted', undefined);
    });
  });

  test('keeps the guided session id when the user switches to the paste route', async () => {
    const onComplete = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.no/,
      }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: START_GUIDED_SESSION_LABEL }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '改用已有智能体整理的画像' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(
        '改用已有智能体整理的画像',
        'pasted',
        'session-1',
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
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
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
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );

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
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );
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
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.profileOnboarding.hasAgent.yes/,
      }),
    );

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
