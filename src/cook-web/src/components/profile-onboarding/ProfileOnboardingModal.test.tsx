import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { createProfileOnboardingSession } from '@/c-api/user';
import ProfileOnboardingModal from './ProfileOnboardingModal';
import { PROFILE_ONBOARDING_EVENTS } from './events';
import enProfile from '../../../../i18n/en-US/modules/profile-onboarding.json';
import frProfile from '../../../../i18n/fr-FR/modules/profile-onboarding.json';
import zhProfile from '../../../../i18n/zh-CN/modules/profile-onboarding.json';

const START_SESSION_LABEL = 'start guided session';
const FINISH_PROFILE_LABEL = 'finish guided profile';
const mockTrackEvent = jest.fn();
const mockScrollTo = jest.fn();
let latestOnDraftReady:
  | ((draft: string, sessionId: string) => void)
  | undefined;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      if (
        key === 'module.profileOnboarding.characterCount' ||
        key === 'module.profileOnboarding.characterCountOverLimit'
      ) {
        return `${params?.count} / ${params?.max}`;
      }
      if (key === 'module.profileOnboarding.stepCounter') {
        return `${params?.current} / ${params?.total}`;
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
          onClick={() => void createSession()}
        >
          {START_SESSION_LABEL}
        </button>
        <button
          type='button'
          disabled={disabled}
          onClick={() => {
            onSessionStarted?.('session-1');
            onDraftReady('引导生成的画像', 'session-1');
          }}
        >
          {FINISH_PROFILE_LABEL}
        </button>
      </div>
    );
  },
}));

const finishGuidedProfile = () => {
  fireEvent.click(screen.getByRole('button', { name: FINISH_PROFILE_LABEL }));
};

describe('ProfileOnboardingModal guided-only flow', () => {
  beforeEach(() => {
    latestOnDraftReady = undefined;
    jest.clearAllMocks();
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      configurable: true,
      value: mockScrollTo,
    });
    (createProfileOnboardingSession as jest.Mock).mockResolvedValue({
      session_id: 'session-1',
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('opens directly on guided questions with a fixed two-step shell', () => {
    render(
      <ProfileOnboardingModal
        open
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    expect(screen.getByTestId('mock-guided-conversation')).toBeInTheDocument();
    expect(
      screen.getByText('module.profileOnboarding.guided.title'),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('module.profileOnboarding.guided.description'),
    ).toHaveLength(1);
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
    expect(screen.getByTestId('profile-onboarding-footer')).toHaveClass(
      'shrink-0',
    );
    const body = screen.getByTestId('profile-onboarding-body');
    expect(body).toHaveClass('motion-reduce:animate-none');
  });

  test('keeps the guided benefit and duration aligned across locales', () => {
    expect(zhProfile.guided.title).toBe('请回答几个问题');
    expect(zhProfile.guided.description).toBe(
      'AI 老师越了解你，讲的课就越容易听懂。大约 1 分钟。',
    );
    expect(enProfile.guided.description).toBe(
      'The better your AI teacher knows you, the easier the lessons are to understand. About 1 minute.',
    );
    expect(frProfile.guided.description).toBe(
      'Plus votre professeur IA vous connaît, plus le cours est facile à comprendre. Environ 1 minute.',
    );
    expect('upgradeDescription' in zhProfile).toBe(false);
    expect('upgradeDescription' in enProfile).toBe(false);
    expect('upgradeDescription' in frProfile).toBe(false);
  });

  test('uses onboarding or settings intent and submits the matching trigger', async () => {
    const onComplete = jest.fn().mockResolvedValue(true);
    const { rerender } = render(
      <ProfileOnboardingModal
        open
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: START_SESSION_LABEL }));
    expect(createProfileOnboardingSession).toHaveBeenCalledWith(
      'zh-CN',
      'onboarding',
    );

    rerender(
      <ProfileOnboardingModal
        open
        sessionIntent='settings'
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: START_SESSION_LABEL }));
    expect(createProfileOnboardingSession).toHaveBeenLastCalledWith(
      'zh-CN',
      'settings',
    );

    finishGuidedProfile();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.save',
      }),
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(
        '引导生成的画像',
        'settings',
        'session-1',
      );
    });
    expect(mockTrackEvent).toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.COMPLETED,
      expect.objectContaining({
        source: 'settings',
        presentation: 'blocking',
      }),
    );
  });

  test('returns from review to the same guided conversation and session', async () => {
    const onComplete = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );
    const conversation = screen.getByTestId('mock-guided-conversation');

    finishGuidedProfile();
    expect(
      screen.getByText('module.profileOnboarding.review.title'),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.back' }),
    );

    expect(screen.getByTestId('mock-guided-conversation')).toBe(conversation);
    expect(
      screen.getByText('module.profileOnboarding.guided.title'),
    ).toHaveFocus();
    expect(createProfileOnboardingSession).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.next' }),
    );
    expect(
      screen.getByText('module.profileOnboarding.review.title'),
    ).toBeInTheDocument();
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

  test('has exactly one explicit defer exit and blocks implicit dismissal', () => {
    const onSkip = jest.fn().mockResolvedValue(true);
    render(
      <ProfileOnboardingModal
        open
        onComplete={jest.fn()}
        onSkip={onSkip}
      />,
    );

    const deferButtons = screen.getAllByRole('button', {
      name: 'module.profileOnboarding.skip',
    });
    expect(deferButtons).toHaveLength(1);
    expect(
      screen.queryByRole('button', { name: 'component.header.close' }),
    ).not.toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.pointerDown(document.body);
    expect(onSkip).not.toHaveBeenCalled();

    fireEvent.click(deferButtons[0]);
    expect(onSkip).toHaveBeenCalledWith(undefined);
  });

  test('keeps skip single-flight and ignores a late guided result', async () => {
    let resolveSkip: (value: boolean) => void = () => undefined;
    const onSkip = jest.fn(
      () =>
        new Promise<boolean>(resolve => {
          resolveSkip = resolve;
        }),
    );
    render(
      <ProfileOnboardingModal
        open
        onComplete={jest.fn()}
        onSkip={onSkip}
      />,
    );

    const defer = screen.getByTestId('profile-onboarding-defer-action');
    fireEvent.click(defer);
    fireEvent.click(defer);
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(defer).toBeDisabled();

    act(() => latestOnDraftReady?.('不应采用的晚到画像', 'late-session'));
    expect(
      screen.queryByText('module.profileOnboarding.review.title'),
    ).not.toBeInTheDocument();

    await act(async () => resolveSkip(true));
  });

  test('preserves a failed draft and validates Unicode code points', async () => {
    const onComplete = jest.fn().mockResolvedValue(false);
    render(
      <ProfileOnboardingModal
        open
        maxLength={2}
        errorMessage='保存失败，请重试'
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );

    act(() => latestOnDraftReady?.('🙂🙂', 'session-unicode'));
    const editor = screen.getByRole('textbox');
    expect(editor).toHaveValue('🙂🙂');
    expect(
      screen.getByText('2 / 2', {
        selector: '#profile-onboarding-review-draft-character-count',
      }),
    ).toBeInTheDocument();
    const complete = screen.getByRole('button', {
      name: 'module.profileOnboarding.complete',
    });
    expect(complete).toBeEnabled();

    fireEvent.change(editor, { target: { value: '🙂🙂🙂' } });
    expect(complete).toBeDisabled();
    fireEvent.change(editor, { target: { value: '🙂🙂' } });
    fireEvent.click(complete);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(editor).toHaveValue('🙂🙂');
    expect(screen.getByRole('alert')).toHaveTextContent('保存失败，请重试');
    expect(complete).toBeEnabled();
  });

  test('focuses route headings and resets scroll during forward and back navigation', async () => {
    render(
      <ProfileOnboardingModal
        open
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    expect(
      screen.getByText('module.profileOnboarding.guided.title'),
    ).toHaveFocus();
    finishGuidedProfile();

    await waitFor(() => {
      expect(
        screen.getByText('module.profileOnboarding.review.title'),
      ).toHaveFocus();
    });
    expect(mockScrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'auto' });
  });

  test('does not render an unusable dialog when guided runtime is unavailable', () => {
    render(
      <ProfileOnboardingModal
        open
        guidedAvailable={false}
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
