import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import ProfileOnboardingConversation, {
  isProfileOnboardingSubmissionWithinLimits,
  resolveProfileDraftFromRunEvent,
  resolveProfileNicknameFromRunEvent,
  type ProfileOnboardingRunSession,
} from './ProfileOnboardingConversation';
import type { ProfileOnboardingAssistantAnswers } from './profileOnboardingConversationModel';

const ANSWER_GUIDED_QUESTION_LABEL = 'answer guided question';
const DEFAULT_RENDERER_SUBMISSION: OnSendContentParams = {
  variableName: 'profile_goal',
  inputText: '学会 AI',
};
let mockRendererSubmission: OnSendContentParams = DEFAULT_RENDERER_SUBMISSION;
let mockAutoFinishTypewriter = true;
let mockLatestTypeFinished: (() => void) | undefined;
let mockRenderedContents: string[] = [];
const mockSendCallbacks = new Map<
  string,
  (value: OnSendContentParams) => void
>();
const mockHintCallbacks = new Map<string, (() => void) | undefined>();
let mockLanguage = 'zh-CN';

type MockScrollControlProps = {
  ariaLabel: string;
  autoScrollOnInit?: boolean;
  bottomOffset?: number;
  contentVersion?: unknown;
  endRef?: React.RefObject<HTMLElement | null>;
  followNewContent?: boolean;
  placement?: string;
  position?: string;
  scrollTarget?: React.RefObject<HTMLElement | null>;
  viewportRef: React.RefObject<HTMLElement | null>;
  zIndex?: number;
};

const mockScrollToBottomControl = jest.fn(
  ({ ariaLabel }: MockScrollControlProps) => (
    <button
      type='button'
      data-testid='profile-scroll-to-bottom-control'
      aria-label={ariaLabel}
    />
  ),
);

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: mockLanguage, resolvedLanguage: mockLanguage },
  }),
}));

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);

jest.mock('markdown-flow-ui/renderer', () => ({
  ContentRender: ({
    content,
    locale,
    lang,
    userInput,
    readonly,
    onSend,
    enableTypewriter,
    typewriterPacing,
    typingSpeed,
    onTypeFinished,
    onPlaceholderAccepted,
  }: {
    content: string;
    locale?: string;
    lang?: string;
    readonly?: boolean;
    userInput?: string;
    onSend?: (value: OnSendContentParams) => void;
    enableTypewriter?: boolean;
    typewriterPacing?: 'fixed' | 'content-aware';
    typingSpeed?: number;
    onTypeFinished?: () => void;
    onPlaceholderAccepted?: () => void;
  }) => {
    mockHintCallbacks.set(content, onPlaceholderAccepted);
    mockRenderedContents.push(content);
    if (onSend) mockSendCallbacks.set(content, onSend);
    React.useEffect(() => {
      mockLatestTypeFinished = onTypeFinished;
      if (mockAutoFinishTypewriter) onTypeFinished?.();
    }, [onTypeFinished]);
    // Match the library's inline custom-variable renderer: an unnecessary
    // MarkdownFlow re-render remounts the input and loses unsent local state.
    const UnsentAnswer = () => (
      <input
        aria-label='unsent question answer'
        defaultValue=''
      />
    );
    return (
      <div
        data-testid='profile-onboarding-renderer'
        data-locale={locale}
        lang={lang}
      >
        <UnsentAnswer />
        <span>{content}</span>
        {userInput ? <span>{userInput}</span> : null}
        <span
          data-testid='profile-onboarding-typewriter'
          data-enabled={String(Boolean(enableTypewriter))}
          data-pacing={typewriterPacing}
          data-speed={String(typingSpeed)}
        />
        {onSend ? (
          <button
            type='button'
            disabled={readonly}
            onClick={() => onSend(mockRendererSubmission)}
          >
            {ANSWER_GUIDED_QUESTION_LABEL}
          </button>
        ) : null}
      </div>
    );
  },
}));

jest.mock('markdown-flow-ui/scroll', () => ({
  ScrollToBottomControl: (props: MockScrollControlProps) =>
    mockScrollToBottomControl(props),
}));

const getLatestScrollControlProps = () => {
  const calls = mockScrollToBottomControl.mock.calls;
  return calls[calls.length - 1]?.[0];
};

describe('ProfileOnboardingConversation', () => {
  beforeEach(() => {
    mockLanguage = 'zh-CN';
    mockRendererSubmission = DEFAULT_RENDERER_SUBMISSION;
    mockAutoFinishTypewriter = true;
    mockLatestTypeFinished = undefined;
    mockRenderedContents = [];
    mockSendCallbacks.clear();
    mockHintCallbacks.clear();
    mockScrollToBottomControl.mockClear();
  });

  test.each(['es-ES', 'ur-PK'])(
    'leaves unknown onboarding content language unset with %s renderer controls',
    async language => {
      mockLanguage = language;
      const runSession = jest.fn(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'spanish-content',
              element_type: 'text',
              content: 'English prompt',
            },
          });
        });
        return { close: jest.fn() };
      });
      render(
        <ProfileOnboardingConversation
          createSession={async () => ({ session_id: 'spanish-session' })}
          runSession={runSession}
          onDraftReady={jest.fn()}
          onError={jest.fn()}
        />,
      );

      await screen.findByText('English prompt');
      expect(screen.getByTestId('profile-onboarding-renderer')).toHaveAttribute(
        'data-locale',
        language,
      );
      expect(screen.getByTestId('profile-onboarding-renderer')).toHaveAttribute(
        'lang',
        '',
      );
    },
  );

  test('matches backend run-input limits using Unicode code points', () => {
    const emoji = '🧠';
    const oneHundredValues = Array.from({ length: 100 }, (_, index) =>
      String.fromCodePoint(0x1000 + index),
    );

    expect(
      isProfileOnboardingSubmissionWithinLimits('v'.repeat(256), [
        emoji.repeat(4_000),
      ]),
    ).toBe(true);
    expect(
      isProfileOnboardingSubmissionWithinLimits('v'.repeat(257), ['answer']),
    ).toBe(false);
    expect(
      isProfileOnboardingSubmissionWithinLimits('profile_goal', [
        emoji.repeat(4_001),
      ]),
    ).toBe(false);
    expect(
      isProfileOnboardingSubmissionWithinLimits(
        'profile_goal',
        oneHundredValues,
      ),
    ).toBe(true);
    expect(
      isProfileOnboardingSubmissionWithinLimits('profile_goal', [
        ...oneHundredValues,
        'extra',
      ]),
    ).toBe(false);
    expect(
      isProfileOnboardingSubmissionWithinLimits('profile_goal', [
        'a'.repeat(4_000),
        'b'.repeat(4_000),
        'c'.repeat(2_000),
      ]),
    ).toBe(true);
    expect(
      isProfileOnboardingSubmissionWithinLimits('profile_goal', [
        'a'.repeat(4_000),
        'b'.repeat(4_000),
        'c'.repeat(2_001),
      ]),
    ).toBe(false);
  });

  test('uses the learning page typewriter cadence for guided content', async () => {
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({
          type: 'element',
          content: {
            element_bid: 'profile-typewriter-content',
            element_type: 'text',
            content: '欢迎，先一起确认你的学习偏好。',
          },
        });
      });
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-typewriter' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    await screen.findByText('欢迎，先一起确认你的学习偏好。');
    const typewriter = screen.getByTestId('profile-onboarding-typewriter');
    expect(typewriter).toHaveAttribute('data-enabled', 'true');
    expect(typewriter).toHaveAttribute('data-pacing', 'content-aware');
    expect(typewriter).toHaveAttribute('data-speed', '30');
  });

  test('renders guided interaction controls without a typewriter delay', async () => {
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({
          type: 'element',
          content: {
            element_bid: 'profile-interaction',
            element_type: 'interaction',
            content: '?[%{{profile_goal}}...What do you want to learn?]',
          },
        });
      });
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-interaction' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    await screen.findByRole('button', {
      name: ANSWER_GUIDED_QUESTION_LABEL,
    });
    expect(screen.getByTestId('profile-onboarding-typewriter')).toHaveAttribute(
      'data-enabled',
      'false',
    );
  });

  test.each([false, true])(
    'forwards completion observers only for editable Profile questions, disabled=%s',
    async disabled => {
      const content = '?[...Describe your background]';
      const observer = jest.fn();
      const runSession: ProfileOnboardingRunSession = ({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'hint-profile',
              element_type: 'interaction',
              content,
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 1 },
          });
        });
        return { close: jest.fn() };
      };
      const props = {
        createSession: async () => ({ session_id: 'hint-session' }),
        runSession,
        onDraftReady: jest.fn(),
        onError: jest.fn(),
        onPlaceholderAccepted: observer,
      };
      const view = render(<ProfileOnboardingConversation {...props} />);
      await screen.findByText(content);
      await waitFor(() =>
        expect(mockHintCallbacks.get(content)).toEqual(expect.any(Function)),
      );
      if (disabled)
        view.rerender(
          <ProfileOnboardingConversation
            {...props}
            disabled
          />,
        );
      act(() => mockHintCallbacks.get(content)?.());
      expect(observer).toHaveBeenCalledTimes(disabled ? 0 : 1);
      view.rerender(
        <ProfileOnboardingConversation
          {...props}
          onPlaceholderAccepted={undefined}
        />,
      );
      expect(mockHintCallbacks.get(content)).toBeUndefined();
    },
  );

  test('renders HTML content without a typewriter delay', async () => {
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({
          type: 'content',
          element_type: 'html',
          generated_block_bid: 'profile-html-content',
          content: '<div>Visual card</div>',
        });
      });
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-html' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    await screen.findByText('<div>Visual card</div>');
    expect(screen.getByTestId('profile-onboarding-typewriter')).toHaveAttribute(
      'data-enabled',
      'false',
    );
  });

  test('keeps an over-limit Unicode answer editable until a valid correction', async () => {
    const onError = jest.fn();
    mockRendererSubmission = {
      variableName: 'profile_goal',
      inputText: '🧠'.repeat(4_001),
    };
    const runSession = jest.fn(({ onMessage }) => {
      if (runSession.mock.calls.length === 1) {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'interaction-over-limit-answer',
              element_type: 'interaction',
              content: '?[%{{profile_goal}}...What would you like to learn?]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 1 },
          });
        });
      }
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-input-limit' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={onError}
      />,
    );

    const answerButton = await screen.findByRole('button', {
      name: ANSWER_GUIDED_QUESTION_LABEL,
    });
    fireEvent.click(answerButton);

    expect(runSession).toHaveBeenCalledTimes(1);
    expect(answerButton).toBeEnabled();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'module.profileOnboarding.guided.inputLimitError',
    );
    expect(onError).not.toHaveBeenCalled();

    mockRendererSubmission = {
      variableName: 'profile_goal',
      inputText: 'Learn practical AI skills',
    };
    fireEvent.click(answerButton);

    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        expectedTurnIndex: 1,
        userInput: { profile_goal: ['Learn practical AI skills'] },
      }),
    );
    expect(
      screen.queryByText('module.profileOnboarding.guided.inputLimitError'),
    ).not.toBeInTheDocument();
  });

  test.each<[string | undefined, string]>([
    ['profile_goal', 'profile_goal'],
    ['你的性别是？', '你的性别是？'],
    ['gender?', 'gender?'],
    ['\u0085gender?\u0085', 'gender?'],
    ['\ufeffgender?\ufeff', '\ufeffgender?\ufeff'],
    ['\ufeff', '\ufeff'],
    ['  user  name  ', 'user  name'],
    [' Which [path] | level//hint...? ', 'Which [path] | level//hint...?'],
    [' a} ', 'a}'],
    [undefined, 'input'],
  ])(
    'submits the exact normalized variable key %s',
    async (variableName, expectedKey) => {
      mockRendererSubmission = { variableName, inputText: '女' };
      const runSession = jest.fn(({ onMessage }) => {
        if (runSession.mock.calls.length === 1) {
          queueMicrotask(() => {
            onMessage({
              type: 'interaction',
              generated_block_bid: 'interaction-question-key',
              interaction_id: 'native-question-key',
              content: `?[%{{${expectedKey}}}...Your answer]`,
            });
            onMessage({
              type: 'done',
              is_terminal: true,
              content: {
                done: false,
                next_turn_index: 1,
                awaiting_input: true,
                pending_interaction_ids: ['native-question-key'],
              },
            });
          });
        }
        return { close: jest.fn() };
      });

      render(
        <ProfileOnboardingConversation
          createSession={async () => ({ session_id: 'session-question-key' })}
          runSession={runSession}
          onDraftReady={jest.fn()}
          onError={jest.fn()}
        />,
      );
      const answerButton = await screen.findByRole('button', {
        name: ANSWER_GUIDED_QUESTION_LABEL,
      });
      await waitFor(() => expect(answerButton).toBeEnabled());
      fireEvent.click(answerButton);

      await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
      expect(runSession.mock.calls[1][0]).toEqual(
        expect.objectContaining({
          expectedTurnIndex: 1,
          expectedInteractionId: 'native-question-key',
          userInput: { [expectedKey]: ['女'] },
        }),
      );
    },
  );

  test('preserves official button values while keeping their display normalized', async () => {
    mockRendererSubmission = {
      variableName: 'style',
      buttonText: ' brief ',
    };
    const runSession = jest.fn(({ onMessage }) => {
      if (runSession.mock.calls.length === 1) {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'interaction-spaced-button-value',
              element_type: 'interaction',
              content: '?[%{{style}}Short// brief ]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 1 },
          });
        });
      } else {
        queueMicrotask(() =>
          onMessage({
            type: 'done',
            is_terminal: true,
            content: {
              done: true,
              input_accepted: true,
              profile_draft: 'Profile',
            },
          }),
        );
      }
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-spaced-value' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    fireEvent.click(
      await screen.findByRole('button', {
        name: ANSWER_GUIDED_QUESTION_LABEL,
      }),
    );

    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        userInput: { style: [' brief '] },
      }),
    );
    expect(await screen.findByText('brief')).toBeInTheDocument();
  });

  test('ignores invalid button values and still trims free-text answers', async () => {
    mockRendererSubmission = {
      variableName: 'style',
      buttonText: '   ',
    };
    const runSession = jest.fn(({ onMessage }) => {
      if (runSession.mock.calls.length === 1) {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'interaction-invalid-button-value',
              element_type: 'interaction',
              content: '?[%{{style}}...How should lessons be explained?]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 1 },
          });
        });
      } else {
        queueMicrotask(() =>
          onMessage({
            type: 'done',
            is_terminal: true,
            content: {
              done: true,
              input_accepted: true,
              profile_draft: 'Profile',
            },
          }),
        );
      }
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-invalid-value' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    const answerButton = await screen.findByRole('button', {
      name: ANSWER_GUIDED_QUESTION_LABEL,
    });
    fireEvent.click(answerButton);
    expect(runSession).toHaveBeenCalledTimes(1);

    mockRendererSubmission = {
      variableName: 'style',
      buttonText: null as unknown as string,
    };
    fireEvent.click(answerButton);
    expect(runSession).toHaveBeenCalledTimes(1);

    mockRendererSubmission = {
      variableName: 'style',
      inputText: '  Explain with examples  ',
    };
    fireEvent.click(answerButton);

    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        userInput: { style: ['Explain with examples'] },
      }),
    );
    expect(
      await screen.findByText('Explain with examples'),
    ).toBeInTheDocument();
  });

  test('waits without progress indicators and keeps input read-only until its cursor arrives', async () => {
    let firstOnMessage: ((event: Record<string, unknown>) => void) | undefined;
    const onRunInFlightChange = jest.fn();
    const runSession = jest.fn(({ onMessage }) => {
      firstOnMessage ??= onMessage;
      return { close: jest.fn() };
    });

    const { container } = render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-terminal-race' })}
        runSession={runSession}
        onRunInFlightChange={onRunInFlightChange}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).not.toBeInTheDocument();
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(1));
    expect(onRunInFlightChange).toHaveBeenLastCalledWith(true);

    act(() => {
      firstOnMessage?.({
        type: 'element',
        content: {
          element_bid: 'welcome-before-interaction',
          element_type: 'content',
          content: 'Let us get to know you.',
        },
      });
    });
    expect(screen.getByText('Let us get to know you.')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).not.toBeInTheDocument();
    expect(
      container.querySelector('.profile-onboarding-markdownflow'),
    ).toHaveAttribute('aria-busy', 'true');

    act(() => {
      firstOnMessage?.({
        type: 'element',
        content: {
          element_bid: 'interaction-before-done',
          element_type: 'interaction',
          content: '?[%{{profile_goal}}...你的学习目标是什么？]',
        },
      });
    });
    const answerButton = await screen.findByRole('button', {
      name: ANSWER_GUIDED_QUESTION_LABEL,
    });
    expect(answerButton).toBeDisabled();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    fireEvent.click(answerButton);
    expect(runSession).toHaveBeenCalledTimes(1);
    expect(onRunInFlightChange).toHaveBeenLastCalledWith(true);

    act(() => {
      firstOnMessage?.({
        type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 1 },
      });
    });
    await waitFor(() => expect(answerButton).toBeEnabled());
    expect(onRunInFlightChange).toHaveBeenLastCalledWith(false);
    fireEvent.click(answerButton);
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
    expect(onRunInFlightChange).toHaveBeenLastCalledWith(true);
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        expectedTurnIndex: 1,
        userInput: { profile_goal: ['学会 AI'] },
      }),
    );
  });

  test('waits without progress indicators after the final response until the draft is ready', async () => {
    mockAutoFinishTypewriter = false;
    let finalOnMessage: ((event: Record<string, unknown>) => void) | undefined;
    const onDraftReady = jest.fn();
    const runSession = jest
      .fn()
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'final-interaction',
              element_type: 'interaction',
              content: '?[%{{profile_goal}}...最后一个问题]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 1 },
          });
        });
        return { close: jest.fn() };
      })
      .mockImplementationOnce(({ onMessage }) => {
        finalOnMessage = onMessage;
        return { close: jest.fn() };
      });

    const { container } = render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-final-progress' })}
        runSession={runSession}
        onDraftReady={onDraftReady}
        onError={jest.fn()}
      />,
    );

    fireEvent.click(
      await screen.findByRole('button', {
        name: ANSWER_GUIDED_QUESTION_LABEL,
      }),
    );
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));

    act(() => {
      finalOnMessage?.({
        type: 'element',
        content: {
          element_bid: 'final-feedback',
          element_type: 'text',
          content: '信息收集完成。',
        },
      });
    });

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).not.toBeInTheDocument();
    expect(
      container.querySelector('.profile-onboarding-markdownflow'),
    ).toHaveAttribute('aria-busy', 'true');
    expect(onDraftReady).not.toHaveBeenCalled();

    act(() => {
      finalOnMessage?.({
        type: 'done',
        is_terminal: true,
        content: { done: true, profile_draft: '最终个人介绍' },
      });
    });

    expect(onDraftReady).not.toHaveBeenCalled();
    act(() => mockLatestTypeFinished?.());
    await waitFor(() =>
      expect(onDraftReady).toHaveBeenCalledWith(
        '最终个人介绍',
        'session-final-progress',
      ),
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  test('makes the active question read-only while the parent action is pending', async () => {
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({
          type: 'element',
          content: {
            element_bid: 'interaction-disabled',
            element_type: 'interaction',
            content: '?[%{{profile_goal}}...你的学习目标是什么？]',
          },
        });
        onMessage({
          type: 'done',
          is_terminal: true,
          content: { done: false },
        });
      });
      return { close: jest.fn() };
    });
    const props = {
      createSession: async () => ({ session_id: 'session-disabled' }),
      runSession,
      onDraftReady: jest.fn(),
      onError: jest.fn(),
    };
    const view = render(<ProfileOnboardingConversation {...props} />);

    const answerButton = await screen.findByRole('button', {
      name: ANSWER_GUIDED_QUESTION_LABEL,
    });
    view.rerender(
      <ProfileOnboardingConversation
        {...props}
        disabled
      />,
    );
    expect(answerButton).toBeDisabled();
    fireEvent.click(answerButton);
    expect(runSession).toHaveBeenCalledTimes(1);

    view.rerender(<ProfileOnboardingConversation {...props} />);
    expect(answerButton).toBeEnabled();
    fireEvent.click(answerButton);
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
  });

  test('does not start provider work when session creation finishes during a parent action', async () => {
    let resolveSession!: (session: { session_id: string }) => void;
    const createSession = jest.fn(
      () =>
        new Promise<{ session_id: string }>(resolve => {
          resolveSession = resolve;
        }),
    );
    const runSession = jest.fn(() => ({ close: jest.fn() }));
    const onSessionStarted = jest.fn();
    const props = {
      createSession,
      runSession,
      onSessionStarted,
      onDraftReady: jest.fn(),
      onError: jest.fn(),
    };
    const view = render(
      <ProfileOnboardingConversation
        {...props}
        disabled
      />,
    );

    await act(async () => {
      resolveSession({ session_id: 'session-created-during-defer' });
    });

    expect(onSessionStarted).toHaveBeenCalledWith(
      'session-created-during-defer',
    );
    expect(runSession).not.toHaveBeenCalled();

    view.rerender(<ProfileOnboardingConversation {...props} />);
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(1));
  });

  test('keeps the question footer inside the sole guided scroller with mobile-safe controls', async () => {
    const runSession = jest.fn(() => ({ close: jest.fn() }));
    const { container } = render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-scroll-layout' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
        questionScrollFooter={<div data-testid='question-scroll-footer' />}
      />,
    );

    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(1));
    const markdownFlow = container.querySelector(
      '.profile-onboarding-markdownflow',
    );

    expect(markdownFlow).toContainElement(
      screen.getByTestId('question-scroll-footer'),
    );
    expect(markdownFlow).toHaveClass(
      'overflow-y-auto',
      'overscroll-contain',
      '[scrollbar-gutter:stable]',
      'max-sm:[&_button]:min-h-11',
      'max-sm:[&_button]:min-w-11',
      'max-sm:[&_input]:min-h-11',
      'max-sm:[&_input]:text-base',
      'max-sm:[&_select]:min-h-11',
      'max-sm:[&_select]:text-base',
      'max-sm:[&_textarea]:text-base',
      'sm:any-pointer-coarse:[&_button]:min-h-11',
      'sm:any-pointer-coarse:[&_button]:min-w-11',
      'sm:any-pointer-coarse:[&_input]:min-h-11',
      'sm:any-pointer-coarse:[&_input]:text-base',
      'sm:any-pointer-coarse:[&_select]:min-h-11',
      'sm:any-pointer-coarse:[&_select]:text-base',
      'sm:any-pointer-coarse:[&_textarea]:text-base',
    );
    expect(container.querySelectorAll('.overflow-y-auto')).toHaveLength(1);
    expect(container.querySelector('.overflow-y-auto')).toBe(markdownFlow);
  });

  test('delegates guided-question scrolling to the library control', async () => {
    const runSession = jest
      .fn()
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'interaction-scroll-1',
              element_type: 'interaction',
              content: '?[%{{profile_goal}}...第一个问题]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 1 },
          });
        });
        return { close: jest.fn() };
      })
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'interaction-scroll-2',
              element_type: 'interaction',
              content: '?[%{{profile_goal}}...第二个问题]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: {
              done: false,
              next_turn_index: 2,
              input_accepted: true,
            },
          });
        });
        return { close: jest.fn() };
      });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-scroll' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    await screen.findByText('?[%{{profile_goal}}...第一个问题]');
    await waitFor(() => {
      expect(getLatestScrollControlProps().contentVersion).toBe(1);
    });

    const firstProps = getLatestScrollControlProps();
    expect(firstProps).toEqual(
      expect.objectContaining({
        ariaLabel: 'common.core.scrollToBottom',
        autoScrollOnInit: true,
        bottomOffset: 36,
        contentVersion: 1,
        followNewContent: false,
        placement: 'bottom-center',
        position: 'absolute',
        zIndex: 10,
      }),
    );
    expect(firstProps).not.toHaveProperty('endRef');
    expect(firstProps.viewportRef).toBe(firstProps.scrollTarget);
    expect(firstProps.viewportRef.current).toHaveClass(
      'profile-onboarding-markdownflow',
    );

    fireEvent.click(
      screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
    );

    await screen.findByText('?[%{{profile_goal}}...第二个问题]');
    await waitFor(() => {
      expect(getLatestScrollControlProps().contentVersion).toBe(2);
    });
  });

  test('updates scroll content version when a gated question becomes visible', async () => {
    mockAutoFinishTypewriter = false;
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({
          type: 'element',
          content: {
            element_bid: 'scroll-guidance',
            element_type: 'text',
            content: 'Read this first',
          },
        });
        onMessage({
          type: 'element',
          content: {
            element_bid: 'scroll-question',
            element_type: 'interaction',
            content: '?[%{{goal}}...Then answer]',
          },
        });
      });
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-scroll-reveal' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    await screen.findByText('Read this first');
    expect(screen.queryByText('?[%{{goal}}...Then answer]')).toBeNull();
    expect(getLatestScrollControlProps().contentVersion).toBe(1);

    act(() => mockLatestTypeFinished?.());

    await screen.findByText('?[%{{goal}}...Then answer]');
    expect(getLatestScrollControlProps().contentVersion).toBe(2);
  });

  test('hides later questions immediately when finished text content changes', async () => {
    mockAutoFinishTypewriter = false;
    let emitMessage: Parameters<ProfileOnboardingRunSession>[0]['onMessage'] =
      () => undefined;
    const runSession = jest.fn(({ onMessage }) => {
      emitMessage = onMessage;
      queueMicrotask(() => {
        onMessage({
          type: 'element',
          content: {
            element_bid: 'changing-guidance',
            element_type: 'text',
            content: 'Initial guidance',
          },
        });
        onMessage({
          type: 'element',
          content: {
            element_bid: 'later-question',
            element_type: 'interaction',
            content: '?[%{{goal}}...Later question]',
          },
        });
      });
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-content-change' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    await screen.findByText('Initial guidance');
    expect(screen.queryByText('?[%{{goal}}...Later question]')).toBeNull();

    act(() => mockLatestTypeFinished?.());
    await screen.findByText('?[%{{goal}}...Later question]');
    const questionRenderCount = mockRenderedContents.filter(
      content => content === '?[%{{goal}}...Later question]',
    ).length;

    act(() => {
      emitMessage({
        type: 'element',
        content: {
          element_bid: 'changing-guidance',
          element_type: 'text',
          content: 'Updated guidance',
        },
      });
    });

    await screen.findByText('Updated guidance');
    expect(screen.queryByText('?[%{{goal}}...Later question]')).toBeNull();
    expect(
      mockRenderedContents.filter(
        content => content === '?[%{{goal}}...Later question]',
      ),
    ).toHaveLength(questionRenderCount);
  });

  test('submits without ES2023 array methods and returns the server profile draft', async () => {
    const onDraftReady = jest.fn();
    const runSession = jest
      .fn()
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'element-1',
              element_type: 'interaction',
              content: '?[%{{profile_goal}}...你的学习目标是什么？]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false },
          });
        });
        return { close: jest.fn() };
      })
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: true, profile_draft: '我的目标是学会 AI。' },
          });
        });
        return { close: jest.fn() };
      });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-1' })}
        runSession={runSession}
        onDraftReady={onDraftReady}
        onError={jest.fn()}
      />,
    );

    await screen.findByText('?[%{{profile_goal}}...你的学习目标是什么？]');
    expect(onDraftReady).not.toHaveBeenCalled();
    const findLastIndexDescriptor = Object.getOwnPropertyDescriptor(
      Array.prototype,
      'findLastIndex',
    );
    if (!findLastIndexDescriptor) {
      throw new Error('Expected the Jest runtime to provide findLastIndex');
    }
    Object.defineProperty(Array.prototype, 'findLastIndex', {
      ...findLastIndexDescriptor,
      value: undefined,
    });
    try {
      fireEvent.click(
        screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
      );
    } finally {
      Object.defineProperty(
        Array.prototype,
        'findLastIndex',
        findLastIndexDescriptor,
      );
    }

    await waitFor(() => {
      expect(runSession).toHaveBeenLastCalledWith(
        expect.objectContaining({
          sessionId: 'session-1',
          expectedTurnIndex: 0,
          requestId: expect.any(String),
          userInput: { profile_goal: ['学会 AI'] },
        }),
      );
      expect(onDraftReady).toHaveBeenCalledWith(
        '我的目标是学会 AI。',
        'session-1',
      );
    });
    expect(runSession.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        expectedTurnIndex: 0,
        requestId: expect.any(String),
        userInput: undefined,
      }),
    );
    expect(runSession.mock.calls[1][0].requestId).not.toBe(
      runSession.mock.calls[0][0].requestId,
    );
  });

  test('continues an unfinished native session without pending interactions using its turn identity', async () => {
    const runSession = jest
      .fn()
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'content-1',
              element_type: 'content',
              content: '先简单介绍一下。',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 4 },
          });
        });
        return { close: jest.fn() };
      })
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'interaction-1',
              element_type: 'interaction',
              content: '?[%{{profile_goal}}...你的学习目标是什么？]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 5 },
          });
        });
        return { close: jest.fn() };
      });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({
          session_id: 'session-auto-next',
          turn_index: 3,
        })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
    expect(runSession.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        sessionId: 'session-auto-next',
        expectedTurnIndex: 3,
        requestId: expect.any(String),
      }),
    );
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        sessionId: 'session-auto-next',
        expectedTurnIndex: 4,
        requestId: expect.any(String),
      }),
    );
    expect(runSession.mock.calls[1][0].requestId).not.toBe(
      runSession.mock.calls[0][0].requestId,
    );
  });

  test('ignores nonterminal done events until the terminal run summary', async () => {
    const close = jest.fn();
    const onDraftReady = jest.fn();
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({
          type: 'element',
          content: {
            element_bid: 'content-before-break',
            element_type: 'content',
            content: '第一段内容',
          },
        });
        onMessage({
          type: 'done',
          is_terminal: false,
          content: '',
        });
        onMessage({
          type: 'element',
          content: {
            element_bid: 'interaction-after-break',
            element_type: 'interaction',
            content: '?[%{{profile_goal}}...继续回答]',
          },
        });
        onMessage({
          type: 'done',
          is_terminal: true,
          content: { done: false, next_turn_index: 4 },
        });
      });
      return { close };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-break' })}
        runSession={runSession}
        onDraftReady={onDraftReady}
        onError={jest.fn()}
      />,
    );

    expect(await screen.findByText('第一段内容')).toBeInTheDocument();
    expect(
      await screen.findByText('?[%{{profile_goal}}...继续回答]'),
    ).toBeInTheDocument();
    expect(close).toHaveBeenCalledTimes(1);
    expect(runSession).toHaveBeenCalledTimes(1);
    expect(onDraftReady).not.toHaveBeenCalled();
  });

  test('does not loop on a native continuation that makes no committed progress', async () => {
    const onError = jest.fn();
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() =>
        onMessage({
          type: 'done',
          is_terminal: true,
          content: {
            done: false,
            awaiting_input: false,
            pending_interaction_ids: [],
            next_turn_index: 3,
          },
        }),
      );
      return { close: jest.fn() };
    });
    render(
      <ProfileOnboardingConversation
        createSession={async () => ({
          session_id: 'no-progress',
          turn_index: 3,
        })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={onError}
      />,
    );
    await screen.findByRole('button', {
      name: 'module.profileOnboarding.guided.retry',
    });
    expect(onError).toHaveBeenCalledTimes(1);
    expect(runSession).toHaveBeenCalledTimes(1);
  });

  test('renders only the first native pending interaction without auto-continuing', async () => {
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        for (const id of ['first', 'second']) {
          onMessage({
            type: 'interaction',
            generated_block_bid: `display-${id}`,
            interaction_id: id,
            content: `?[...${id}]`,
          });
        }
        onMessage({
          type: 'done',
          is_terminal: true,
          content: {
            done: false,
            awaiting_input: true,
            pending_interaction_ids: ['first', 'second'],
            next_turn_index: 1,
          },
        });
      });
      return { close: jest.fn() };
    });
    render(
      <ProfileOnboardingConversation
        createSession={async () => ({
          session_id: 'pending-batch',
          turn_index: 0,
        })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );
    expect(await screen.findByText('?[...first]')).toBeInTheDocument();
    expect(screen.queryByText('?[...second]')).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
    );
    expect(runSession.mock.calls[1][0]).toMatchObject({
      expectedTurnIndex: 1,
      expectedInteractionId: 'first',
    });
  });

  test('keeps same-tick elements without server ids distinct', async () => {
    const dateNow = jest.spyOn(Date, 'now').mockReturnValue(1234);
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({ type: 'content', content: '无 ID 内容一' });
        onMessage({ type: 'content', content: '无 ID 内容二' });
        onMessage({
          type: 'done',
          is_terminal: true,
          content: { done: true, profile_draft: '最终画像' },
        });
      });
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-fallback-ids' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    expect(await screen.findByText('无 ID 内容一')).toBeInTheDocument();
    expect(screen.getByText('无 ID 内容二')).toBeInTheDocument();
    dateNow.mockRestore();
  });

  test('accepts profile draft summaries encoded as JSON strings', () => {
    expect(
      resolveProfileDraftFromRunEvent({
        type: 'done',
        content: JSON.stringify({ profile_draft: '画像草稿' }),
      }),
    ).toBe('画像草稿');
    expect(
      resolveProfileNicknameFromRunEvent({
        type: 'done',
        content: JSON.stringify({ nickname: ' 小雨 ' }),
      }),
    ).toBe('小雨');
  });

  test('hands the terminal profile draft to the editor without rendering it in the conversation', async () => {
    const onDraftReady = jest.fn();
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({
          type: 'done',
          is_terminal: true,
          content: {
            done: true,
            profile_draft: '只进入编辑框的个人介绍',
            nickname: '小雨',
          },
        });
      });
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-terminal-draft' })}
        runSession={runSession}
        onDraftReady={onDraftReady}
        onError={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(onDraftReady).toHaveBeenCalledWith(
        '只进入编辑框的个人介绍',
        'session-terminal-draft',
        '小雨',
      ),
    );
    expect(
      screen.queryByText('只进入编辑框的个人介绍'),
    ).not.toBeInTheDocument();
  });

  test('ignores a trailing done event after a runtime error', async () => {
    const onDraftReady = jest.fn();
    const onError = jest.fn();
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => {
        onMessage({ type: 'error', content: 'runtime failed' });
        onMessage({
          type: 'done',
          is_terminal: true,
          content: { done: true, profile_draft: '不应采用的画像' },
        });
      });
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-error' })}
        runSession={runSession}
        onDraftReady={onDraftReady}
        onError={onError}
      />,
    );

    await waitFor(() => {
      expect(onError).toHaveBeenCalledTimes(1);
      expect(runSession).toHaveBeenCalledTimes(1);
    });
    expect(onError.mock.calls[0][0]).toEqual(
      new Error('module.profileOnboarding.guided.retryableError'),
    );
    expect(onError.mock.calls[0][0].message).not.toContain('runtime failed');
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveClass('order-first', 'pt-6');
    expect(screen.getByRole('status')).not.toHaveClass('pb-6');
    expect(onDraftReady).not.toHaveBeenCalled();
  });

  test.each(['Robin', ''])(
    'completes a manual nickname-only session only when a nickname exists: %s',
    async nickname => {
      const onDraftReady = jest.fn();
      const onError = jest.fn();
      const runSession = jest.fn(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({ type: 'phase', content: { phase: 'summary' } });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: {
              done: true,
              profile_draft: '',
              nickname,
              next_turn_index: 1,
              pending_interaction_ids: [],
              awaiting_input: false,
            },
          });
        });
        return { close: jest.fn() };
      });
      render(
        <ProfileOnboardingConversation
          createSession={async () => ({
            session_id: 'nickname-only-manual',
            turn_index: 0,
          })}
          runSession={runSession}
          onDraftReady={onDraftReady}
          onError={onError}
        />,
      );
      if (nickname) {
        await waitFor(() =>
          expect(onDraftReady).toHaveBeenCalledWith(
            '',
            'nickname-only-manual',
            nickname,
          ),
        );
        expect(onError).not.toHaveBeenCalled();
      } else {
        await waitFor(() =>
          expect(onError).toHaveBeenCalledWith(
            new Error('module.profileOnboarding.guided.missingDraft'),
          ),
        );
        expect(onDraftReady).not.toHaveBeenCalled();
      }
      expect(runSession).toHaveBeenCalledTimes(1);
    },
  );

  test('binds normalized keys to the current interaction, rejects stale answers, and retries the same answer', async () => {
    const variableKey = 'Which [path] |  level//hint...?';
    mockRendererSubmission = {
      variableName: `\u0085${variableKey}\u0085`,
      inputText: 'Learn practical AI skills',
    };
    const emitQuestion = (
      onMessage: Parameters<ProfileOnboardingRunSession>[0]['onMessage'],
      id: string,
    ) => {
      onMessage({
        type: 'interaction',
        generated_block_bid: `display-${id}`,
        interaction_id: id,
        content: `?[...${id}]`,
      });
      onMessage({
        type: 'done',
        is_terminal: true,
        content: {
          done: false,
          next_turn_index: 0,
          input_accepted: id === 'native-question-2',
          awaiting_input: true,
          pending_interaction_ids: [id],
        },
      });
    };
    const runSession = jest
      .fn()
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => emitQuestion(onMessage, 'native-question-1'));
        return { close: jest.fn() };
      })
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => emitQuestion(onMessage, 'native-question-2'));
        return { close: jest.fn() };
      })
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() =>
          onMessage({
            type: 'error',
            content: 'transient_markdownflow_session_busy',
          }),
        );
        return { close: jest.fn() };
      })
      .mockImplementation(() => ({ close: jest.fn() }));

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'native-session' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    const firstAnswerButton = await screen.findByRole('button', {
      name: ANSWER_GUIDED_QUESTION_LABEL,
    });
    const staleSend = mockSendCallbacks.get('?[...native-question-1]');
    expect(staleSend).toBeDefined();
    fireEvent.click(firstAnswerButton);
    await screen.findByText('?[...native-question-2]');
    expect(runSession.mock.calls[1][0]).toMatchObject({
      expectedTurnIndex: 0,
      expectedInteractionId: 'native-question-1',
      userInput: { [variableKey]: ['Learn practical AI skills'] },
    });
    act(() => staleSend?.(mockRendererSubmission));
    expect(runSession).toHaveBeenCalledTimes(2);
    fireEvent.click(
      screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
    );
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    );
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(4));
    expect(runSession.mock.calls[2][0]).toMatchObject({
      expectedTurnIndex: 0,
      expectedInteractionId: 'native-question-2',
      userInput: { [variableKey]: ['Learn practical AI skills'] },
    });
    expect(runSession.mock.calls[3][0]).toMatchObject({
      expectedInteractionId: 'native-question-2',
      requestId: runSession.mock.calls[2][0].requestId,
      userInput: runSession.mock.calls[2][0].userInput,
    });
  });

  test('keeps one native session across validation and multiple pending interactions before summarizing', async () => {
    const createSession = jest.fn(async () => ({
      session_id: 'whole-questionnaire',
      turn_index: 0,
    }));
    const onDraftReady = jest.fn();
    const onError = jest.fn();
    const runSession = jest.fn(({ onMessage }) => {
      const turn = runSession.mock.calls.length;
      queueMicrotask(() => {
        if (turn === 1) {
          onMessage({
            type: 'content',
            generated_block_bid: 'welcome',
            content: 'Welcome to the complete questionnaire',
          });
        }
        if (turn === 2) {
          onMessage({
            type: 'content',
            generated_block_bid: 'validation',
            content: 'Please explain your goal more clearly',
          });
        }
        if (turn < 4) {
          const interactionId = turn === 3 ? 'question-two' : 'question-one';
          onMessage({
            type: 'interaction',
            generated_block_bid: `turn-${turn}:interaction`,
            interaction_id: interactionId,
            content:
              turn === 3 ? '?[...Second question]' : '?[...First question]',
          });
          // A trailing text event must not conceal the pending interaction.
          onMessage({
            type: 'content',
            generated_block_bid: `guidance-${turn}`,
            content: `Guidance for native turn ${turn}`,
          });
        } else {
          onMessage({ type: 'phase', content: { phase: 'summary' } });
        }
        onMessage({
          type: 'done',
          is_terminal: true,
          content: {
            session_id: 'whole-questionnaire',
            turn_index: turn - 1,
            next_turn_index: turn,
            done: turn === 4,
            awaiting_input: turn < 4,
            input_accepted: turn >= 3,
            pending_interaction_ids:
              turn < 3
                ? ['question-one', 'question-two']
                : turn === 3
                  ? ['question-two']
                  : [],
            ...(turn === 4
              ? { profile_draft: 'Validated learner profile' }
              : {}),
          },
        });
      });
      return { close: jest.fn() };
    });
    render(
      <ProfileOnboardingConversation
        createSession={createSession}
        runSession={runSession}
        onDraftReady={onDraftReady}
        onError={onError}
      />,
    );

    const firstAnswer = await screen.findByRole('button', {
      name: ANSWER_GUIDED_QUESTION_LABEL,
    });
    expect(firstAnswer).toBeEnabled();
    expect(runSession).toHaveBeenCalledTimes(1);
    fireEvent.click(firstAnswer);
    await screen.findByText('Please explain your goal more clearly');
    const correctedAnswer = screen.getByRole('button', {
      name: ANSWER_GUIDED_QUESTION_LABEL,
    });
    expect(correctedAnswer).toBeEnabled();
    expect(screen.queryByText('学会 AI')).not.toBeInTheDocument();
    expect(runSession.mock.calls[1][0]).toMatchObject({
      expectedTurnIndex: 1,
      expectedInteractionId: 'question-one',
    });

    fireEvent.click(correctedAnswer);
    await screen.findByText('?[...Second question]');
    expect(await screen.findByText('学会 AI')).toBeInTheDocument();
    expect(runSession.mock.calls[2][0]).toMatchObject({
      expectedTurnIndex: 2,
      expectedInteractionId: 'question-one',
    });
    fireEvent.click(
      screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
    );
    await waitFor(() =>
      expect(onDraftReady).toHaveBeenCalledWith(
        'Validated learner profile',
        'whole-questionnaire',
      ),
    );
    expect(runSession.mock.calls[3][0]).toMatchObject({
      expectedTurnIndex: 3,
      expectedInteractionId: 'question-two',
    });
    expect(createSession).toHaveBeenCalledTimes(1);
    expect(runSession).toHaveBeenCalledTimes(4);
    expect(onError).not.toHaveBeenCalled();
    expect(
      screen.getByText('Welcome to the complete questionnaire'),
    ).toBeInTheDocument();
  });

  test('retries a retryable SSE failure in the same session with the same user input', async () => {
    const createSession = jest
      .fn()
      .mockResolvedValue({ session_id: 'session-retry' });
    const onError = jest.fn();
    const onRetry = jest.fn();
    const runSession = jest
      .fn()
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'element-retry',
              element_type: 'interaction',
              content: '?[%{{profile_goal}}...你的学习目标是什么？]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 1 },
          });
        });
        return { close: jest.fn() };
      })
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'error',
            content: 'transient_markdownflow_session_busy',
          });
        });
        return { close: jest.fn() };
      })
      .mockImplementationOnce(() => ({ close: jest.fn() }));

    render(
      <ProfileOnboardingConversation
        createSession={createSession}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={onError}
        onRetry={onRetry}
      />,
    );

    await screen.findByText('?[%{{profile_goal}}...你的学习目标是什么？]');
    fireEvent.click(
      screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
    );
    const retryButton = await screen.findByRole('button', {
      name: 'module.profileOnboarding.guided.retry',
    });
    expect(screen.getByRole('status')).toHaveClass('pb-6');
    expect(screen.getByRole('status')).not.toHaveClass('order-first', 'pt-6');
    expect(onError.mock.calls[0][0]).toEqual(
      new Error('module.profileOnboarding.guided.retryableError'),
    );
    expect(onError.mock.calls[0][0].message).not.toContain(
      'transient_markdownflow_session_busy',
    );

    fireEvent.click(retryButton);

    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(3));
    expect(createSession).toHaveBeenCalledTimes(1);
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        sessionId: 'session-retry',
        expectedTurnIndex: 1,
        requestId: expect.any(String),
        userInput: { profile_goal: ['学会 AI'] },
      }),
    );
    expect(runSession.mock.calls[2][0]).toEqual(
      expect.objectContaining({
        sessionId: 'session-retry',
        expectedTurnIndex: 1,
        requestId: expect.any(String),
        userInput: { profile_goal: ['学会 AI'] },
      }),
    );
    expect(runSession.mock.calls[2][0].requestId).toBe(
      runSession.mock.calls[1][0].requestId,
    );
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  test('offers the same-session retry after a network error without exposing details', async () => {
    const createSession = jest
      .fn()
      .mockResolvedValue({ session_id: 'session-network' });
    const onError = jest.fn();
    const runSession = jest
      .fn()
      .mockImplementationOnce(({ onError: fail }) => {
        queueMicrotask(() =>
          fail(new Error('socket ECONNRESET internal-host')),
        );
        return { close: jest.fn() };
      })
      .mockImplementationOnce(() => ({ close: jest.fn() }));

    render(
      <ProfileOnboardingConversation
        createSession={createSession}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={onError}
      />,
    );

    const retryButton = await screen.findByRole('button', {
      name: 'module.profileOnboarding.guided.retry',
    });
    expect(onError.mock.calls[0][0]).toEqual(
      new Error('module.profileOnboarding.guided.retryableError'),
    );
    expect(onError.mock.calls[0][0].message).not.toContain('ECONNRESET');

    fireEvent.click(retryButton);

    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
    expect(createSession).toHaveBeenCalledTimes(1);
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        sessionId: 'session-network',
        expectedTurnIndex: 0,
        requestId: expect.any(String),
        userInput: undefined,
      }),
    );
    expect(runSession.mock.calls[1][0].requestId).toBe(
      runSession.mock.calls[0][0].requestId,
    );
  });

  test('recovers an expired Redis session with a fresh session and request', async () => {
    const createSession = jest
      .fn()
      .mockResolvedValueOnce({
        session_id: 'stale-session',
        turn_index: 2,
      })
      .mockResolvedValueOnce({
        session_id: 'fresh-session',
        turn_index: 7,
      });
    const onError = jest.fn();
    const onRetry = jest.fn();
    const onSessionStarted = jest.fn();
    const runSession = jest
      .fn()
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'element',
            content: {
              element_bid: 'stale-session-question',
              element_type: 'interaction',
              content: '?[%{{profile_goal}}...你的学习目标是什么？]',
            },
          });
          onMessage({
            type: 'done',
            is_terminal: true,
            content: { done: false, next_turn_index: 3 },
          });
        });
        return { close: jest.fn() };
      })
      .mockImplementationOnce(({ onMessage }) => {
        queueMicrotask(() => {
          onMessage({
            type: 'error',
            content: 'transient_markdownflow_session_not_found',
          });
        });
        return { close: jest.fn() };
      })
      .mockImplementationOnce(() => ({ close: jest.fn() }));

    render(
      <ProfileOnboardingConversation
        createSession={createSession}
        runSession={runSession}
        onSessionStarted={onSessionStarted}
        onDraftReady={jest.fn()}
        onError={onError}
        onRetry={onRetry}
      />,
    );

    await screen.findByText('?[%{{profile_goal}}...你的学习目标是什么？]');
    fireEvent.click(
      screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
    );

    const retryButton = await screen.findByRole('button', {
      name: 'module.profileOnboarding.guided.retry',
    });
    expect(onError).toHaveBeenCalledWith(
      new Error('module.profileOnboarding.guided.retryableError'),
    );
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        sessionId: 'stale-session',
        expectedTurnIndex: 3,
        requestId: expect.any(String),
        userInput: { profile_goal: ['学会 AI'] },
      }),
    );

    fireEvent.click(retryButton);

    await waitFor(() => expect(createSession).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(3));
    expect(runSession.mock.calls[2][0]).toEqual(
      expect.objectContaining({
        sessionId: 'fresh-session',
        expectedTurnIndex: 7,
        requestId: expect.any(String),
        userInput: undefined,
      }),
    );
    expect(runSession.mock.calls[2][0].requestId).not.toBe(
      runSession.mock.calls[1][0].requestId,
    );
    expect(onSessionStarted.mock.calls).toEqual([
      ['stale-session'],
      ['fresh-session'],
    ]);
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByText('?[%{{profile_goal}}...你的学习目标是什么？]'),
    ).not.toBeInTheDocument();
  });

  test('does not offer retry for an invalid MarkdownFlow SSE error', async () => {
    const errorCode = 'transient_markdownflow_invalid';
    const onError = jest.fn();
    const runSession = jest.fn(({ onMessage }) => {
      queueMicrotask(() => onMessage({ type: 'error', content: errorCode }));
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-terminal-error' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={onError}
      />,
    );

    await waitFor(() => expect(onError).toHaveBeenCalledTimes(1));
    expect(onError.mock.calls[0][0]).toEqual(
      new Error('module.profileOnboarding.guided.streamError'),
    );
    expect(onError.mock.calls[0][0].message).not.toContain(errorCode);
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    ).not.toBeInTheDocument();
  });

  test('retries session creation with a fresh session after a transient failure', async () => {
    const onError = jest.fn();
    const busyError = Object.assign(new Error('busy'), {
      code: 4013,
      status: 200,
    });
    const createSession = jest
      .fn()
      .mockRejectedValueOnce(busyError)
      .mockResolvedValueOnce({ session_id: 'session-after-retry' });
    const runSession = jest.fn((params: unknown) => {
      void params;
      return { close: jest.fn() };
    });
    render(
      <ProfileOnboardingConversation
        createSession={createSession}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={onError}
      />,
    );

    await waitFor(() => expect(onError).toHaveBeenCalledTimes(1));
    expect(onError.mock.calls[0][0]).toEqual(
      new Error('module.profileOnboarding.guided.streamError'),
    );
    expect(onError.mock.calls[0][0].message).not.toContain('busy');
    const retry = screen.getByRole('button', {
      name: 'module.profileOnboarding.guided.retry',
    });
    fireEvent.click(retry);

    await waitFor(() => expect(createSession).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(1));
    expect(runSession.mock.calls[0][0]).toEqual(
      expect.objectContaining({ sessionId: 'session-after-retry' }),
    );
  });

  test('refreshes eligibility instead of retrying a rejected session create', async () => {
    const rejection = Object.assign(new Error('parameter error: intent'), {
      code: 2001,
      status: 200,
    });
    const onError = jest.fn();
    const onSessionCreateRejected = jest.fn();

    render(
      <ProfileOnboardingConversation
        createSession={jest.fn().mockRejectedValue(rejection)}
        runSession={jest.fn(() => ({ close: jest.fn() }))}
        onDraftReady={jest.fn()}
        onError={onError}
        onSessionCreateRejected={onSessionCreateRejected}
      />,
    );

    await waitFor(() =>
      expect(onSessionCreateRejected).toHaveBeenCalledWith(rejection),
    );
    expect(onError).not.toHaveBeenCalled();
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    ).not.toBeInTheDocument();
  });

  test('does not recreate the server session when callback props change', async () => {
    const createSession = jest
      .fn()
      .mockResolvedValue({ session_id: 'session-stable' });
    const firstRunSession = jest.fn(() => ({ close: jest.fn() }));
    const { rerender } = render(
      <ProfileOnboardingConversation
        createSession={createSession}
        runSession={firstRunSession}
        onDraftReady={() => undefined}
        onError={() => undefined}
        onRetry={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledTimes(1);
      expect(firstRunSession).toHaveBeenCalledTimes(1);
    });

    rerender(
      <ProfileOnboardingConversation
        createSession={createSession}
        runSession={() => ({ close: jest.fn() })}
        onSessionStarted={() => undefined}
        onDraftReady={() => undefined}
        onError={() => undefined}
        onRetry={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledTimes(1);
      expect(firstRunSession).toHaveBeenCalledTimes(1);
    });
  });
});

describe('assistant answers in the existing session', () => {
  const begin = async (
    assistantPrompt = 'Shared research questions',
    questionPending = false,
  ) => {
    const createSession = jest.fn(async () => ({
      session_id: 'shared-session',
      assistant_prompt: assistantPrompt,
    }));
    const runSession = jest.fn(
      ({ onMessage }: Parameters<ProfileOnboardingRunSession>[0]) => {
        if (questionPending) return { close: jest.fn() };
        onMessage({
          event_type: 'interaction',
          content: 'Question one',
          generated_block_bid: 'one',
        });
        onMessage({
          event_type: 'done',
          is_terminal: true,
          content: { done: false, next_turn_index: 2 },
        });
        return { close: jest.fn() };
      },
    );
    const assistantAnswers = jest.fn<
      ReturnType<ProfileOnboardingAssistantAnswers>,
      Parameters<ProfileOnboardingAssistantAnswers>
    >(() => ({ close: jest.fn() }));
    const onAssistantDraftReady = jest.fn();
    const onDraftReady = jest.fn();
    const onError = jest.fn();
    const onCollectionRouteChosen = jest.fn();
    const onAssistantOpened = jest.fn();
    const onAssistantAttempt = jest.fn();
    const onAssistantResult = jest.fn();
    const renderConversation = (
      draft = 'External answer',
      disabled = false,
    ) => (
      <ProfileOnboardingConversation
        createSession={createSession}
        runSession={runSession}
        assistantAnswers={assistantAnswers}
        assistantDraft={draft}
        onAssistantDraftChange={jest.fn()}
        onAssistantDraftReady={onAssistantDraftReady}
        onCollectionRouteChosen={onCollectionRouteChosen}
        onAssistantOpened={onAssistantOpened}
        onAssistantAttempt={onAssistantAttempt}
        onAssistantResult={onAssistantResult}
        onDraftReady={onDraftReady}
        onError={onError}
        disabled={disabled}
      />
    );
    const result = render(renderConversation());
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(1));
    return {
      ...result,
      createSession,
      runSession,
      assistantAnswers,
      onAssistantDraftReady,
      onCollectionRouteChosen,
      onAssistantOpened,
      onAssistantAttempt,
      onAssistantResult,
      onDraftReady,
      onError,
      renderConversation,
    };
  };
  const enter = () =>
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.entry',
      }),
    );
  const process = () =>
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.process',
      }),
    );

  test('reports explicit route choices and keeps navigation fail-open', async () => {
    const result = await begin();

    enter();
    expect(result.onCollectionRouteChosen).toHaveBeenCalledWith('ai_assistant');
    expect(result.onAssistantOpened).toHaveBeenCalledTimes(1);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.back',
      }),
    );
    expect(result.onCollectionRouteChosen).toHaveBeenCalledWith(
      'guided_questions',
    );

    result.onCollectionRouteChosen.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    enter();
    expect(
      screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
    ).toBeVisible();
    expect(result.onAssistantOpened).toHaveBeenCalledTimes(2);
  });

  test('reports one assistant attempt and its successful terminal result', async () => {
    const result = await begin();
    enter();
    process();

    expect(result.onAssistantAttempt).toHaveBeenCalledTimes(1);
    expect(result.onAssistantResult).not.toHaveBeenCalled();

    act(() => {
      result.assistantAnswers.mock.calls[0][0].onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: true, profile_draft: 'Imported profile' },
      });
    });

    expect(result.onAssistantResult).toHaveBeenCalledTimes(1);
    expect(result.onAssistantResult).toHaveBeenCalledWith('success', undefined);
  });

  test('maps assistant runtime failures to a bounded terminal category', async () => {
    const result = await begin();
    enter();
    process();

    act(() => {
      result.assistantAnswers.mock.calls[0][0].onMessage({
        event_type: 'error',
        content: 'private backend detail',
      });
    });

    expect(result.onAssistantResult).toHaveBeenCalledTimes(1);
    expect(result.onAssistantResult).toHaveBeenCalledWith(
      'failed',
      'runtime_failed',
    );
    expect(JSON.stringify(result.onAssistantResult.mock.calls)).not.toContain(
      'private backend detail',
    );
  });

  test('offers copying before the first question and keeps its stream alive when returning', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const result = await begin('Shared research questions', true);
    const entry = screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.entry',
    });
    expect(entry).toBeEnabled();
    expect(
      screen.getByTestId('profile-onboarding-conversation'),
    ).toHaveAttribute('aria-busy', 'false');
    expect(screen.queryByText('Question one')).not.toBeInTheDocument();
    expect(entry.parentElement).toContainElement(
      screen.getByLabelText('unsent question answer'),
    );
    expect(entry.closest('[aria-busy="true"]')).toBeNull();
    expect(
      screen.getByRole('button', { name: 'common.core.scrollToBottom' }),
    ).toBeInTheDocument();
    enter();
    expect(
      screen.queryByRole('button', { name: 'common.core.scrollToBottom' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
    ).toBeEnabled();
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.assistant.copy',
        }),
      );
    });
    expect(writeText).toHaveBeenCalledWith('Shared research questions');
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.process',
      }),
    ).toBeEnabled();
    expect(
      screen.queryByText(
        'module.profileOnboarding.assistant.waitingForQuestion',
      ),
    ).not.toBeInTheDocument();
    expect(result.assistantAnswers).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.back',
      }),
    );
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.entry',
      }),
    ).toHaveFocus();
    expect(
      screen.getByRole('button', { name: 'common.core.scrollToBottom' }),
    ).toBeInTheDocument();
    expect(
      result.runSession.mock.results[0].value.close,
    ).not.toHaveBeenCalled();
    enter();
    act(() => {
      result.runSession.mock.calls[0][0].onMessage({
        event_type: 'interaction',
        content: 'Question one',
        generated_block_bid: 'one',
      });
      result.runSession.mock.calls[0][0].onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 2 },
      });
    });
    expect(screen.getByText('Question one')).not.toBeVisible();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.process',
      }),
    ).toBeEnabled();
    expect(result.assistantAnswers).not.toHaveBeenCalled();
    process();
    expect(result.assistantAnswers).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: 'shared-session',
        expectedTurnIndex: 2,
        rawText: 'External answer',
      }),
    );
    expect(result.createSession).toHaveBeenCalledTimes(1);
    expect(result.runSession).toHaveBeenCalledTimes(1);
  });

  test.each([
    ['zh-CN', '请根据你对我的了解，回答这些问题。'],
    ['fr-FR', 'Réponds à ces questions selon ce que tu sais de moi.'],
    ['ar-SA', 'أجب عن هذه الأسئلة بناءً على ما تعرفه عني.'],
  ])(
    'displays and copies the exact %s session prompt',
    async (_locale, prompt) => {
      const writeText = jest.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText },
      });
      await begin(prompt, true);

      enter();
      expect(screen.getByText(prompt)).toBeVisible();
      await act(async () => {
        fireEvent.click(
          screen.getByRole('button', {
            name: 'module.profileOnboarding.assistant.copy',
          }),
        );
      });

      expect(writeText).toHaveBeenCalledWith(prompt);
    },
  );

  test('accepts one early click and imports at the first content-only boundary', async () => {
    const result = await begin('Shared research questions', true);
    const first = result.runSession.mock.calls[0][0];
    enter();
    process();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.processing',
      }),
    ).toBeDisabled();
    expect(
      screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.back',
      }),
    ).toBeDisabled();
    expect(result.assistantAnswers).not.toHaveBeenCalled();
    expect(
      result.runSession.mock.results[0].value.close,
    ).not.toHaveBeenCalled();
    result.rerender(result.renderConversation('Changed after the click'));
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.processing',
      }),
    );
    await act(async () => {
      first.onMessage({ event_type: 'content', content: 'Welcome' });
      first.onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 1 },
      });
    });
    expect(result.assistantAnswers).toHaveBeenCalledTimes(1);
    expect(result.assistantAnswers.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        sessionId: 'shared-session',
        expectedTurnIndex: 1,
        rawText: 'External answer',
        requestId: expect.stringContaining('profile-onboarding-assistant-'),
      }),
    );
    act(() => {
      first.onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 8 },
      });
      result.assistantAnswers.mock.calls[0][0].onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: true, profile_draft: 'Imported profile' },
      });
    });
    expect(result.onAssistantDraftReady).toHaveBeenCalledWith(
      'Imported profile',
      'shared-session',
      undefined,
    );
    expect(result.onDraftReady).not.toHaveBeenCalled();
    expect(result.runSession).toHaveBeenCalledTimes(1);
    expect(result.createSession).toHaveBeenCalledTimes(1);
  });

  test('replays an uncertain ordinary request before handing off the accepted paste', async () => {
    const result = await begin('Shared research questions', true);
    const first = result.runSession.mock.calls[0][0];
    enter();
    process();
    act(() => first.onError(new Error('Disconnected')));
    expect(result.assistantAnswers).not.toHaveBeenCalled();
    expect(
      screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
    ).toBeDisabled();
    result.rerender(result.renderConversation('Do not use this new body'));
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    );
    const replay = result.runSession.mock.calls[1][0];
    expect(replay).toEqual(
      expect.objectContaining({
        requestId: first.requestId,
        expectedTurnIndex: first.expectedTurnIndex,
        userInput: first.userInput,
      }),
    );
    await act(async () =>
      replay.onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 1 },
      }),
    );
    expect(result.assistantAnswers).toHaveBeenCalledTimes(1);
    expect(result.assistantAnswers.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        expectedTurnIndex: 1,
        rawText: 'External answer',
      }),
    );
    expect(result.runSession).toHaveBeenCalledTimes(2);
  });

  test('finishes an in-flight manual answer before importing at its committed cursor', async () => {
    const result = await begin();
    result.runSession.mockImplementationOnce(() => ({ close: jest.fn() }));
    fireEvent.click(
      screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
    );
    const manual = result.runSession.mock.calls[1][0];
    expect(manual.userInput).toEqual({ profile_goal: ['学会 AI'] });
    enter();
    process();
    expect(result.assistantAnswers).not.toHaveBeenCalled();
    await act(async () =>
      manual.onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 3 },
      }),
    );
    expect(result.assistantAnswers.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        expectedTurnIndex: 3,
        rawText: 'External answer',
      }),
    );
    expect(result.runSession).toHaveBeenCalledTimes(2);
  });

  test('an import click wins over an already scheduled ordinary continuation', async () => {
    const result = await begin('Shared research questions', true);
    enter();
    await act(async () => {
      result.runSession.mock.calls[0][0].onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 1 },
      });
      process();
    });
    expect(result.assistantAnswers).toHaveBeenCalledTimes(1);
    expect(result.runSession).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.processing',
      }),
    ).toBeDisabled();
    expect(
      screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
    ).toBeDisabled();
  });

  test('holds a confirmed handoff while externally disabled and resumes it once', async () => {
    const result = await begin('Shared research questions', true);
    enter();
    process();
    result.rerender(result.renderConversation('External answer', true));
    await act(async () =>
      result.runSession.mock.calls[0][0].onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 1 },
      }),
    );
    expect(result.assistantAnswers).not.toHaveBeenCalled();
    result.rerender(result.renderConversation());
    expect(result.assistantAnswers).toHaveBeenCalledTimes(1);
    expect(result.runSession).toHaveBeenCalledTimes(1);
  });

  test('returns from a rejected early import by generating the next question in the same session', async () => {
    const result = await begin('Shared research questions', true);
    enter();
    process();
    await act(async () =>
      result.runSession.mock.calls[0][0].onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 1 },
      }),
    );
    act(() =>
      result.assistantAnswers.mock.calls[0][0].onMessage({
        event_type: 'error',
        content: 'transient_markdownflow_invalid',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.back',
      }),
    );
    expect(result.runSession).toHaveBeenCalledTimes(2);
    expect(result.runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        sessionId: 'shared-session',
        expectedTurnIndex: 1,
        userInput: undefined,
      }),
    );
    expect(result.createSession).toHaveBeenCalledTimes(1);
  });

  test('a queued import takes the confirmed native turn before continuation starts', async () => {
    const result = await begin('Shared research questions', true);
    enter();
    process();
    await act(async () =>
      result.runSession.mock.calls[0][0].onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: false, next_turn_index: 1 },
      }),
    );
    expect(result.assistantAnswers.mock.calls[0][0].expectedTurnIndex).toBe(1);
    expect(result.runSession).toHaveBeenCalledTimes(1);
  });

  test.each(['unmount', 'fatal', 'expired'] as const)(
    '%s discards a queued handoff instead of importing into another session',
    async ending => {
      const result = await begin('Shared research questions', true);
      const first = result.runSession.mock.calls[0][0];
      enter();
      process();
      if (ending === 'unmount') {
        result.unmount();
      } else {
        act(() =>
          first.onMessage({
            event_type: 'error',
            content:
              ending === 'fatal'
                ? 'transient_markdownflow_invalid'
                : 'transient_markdownflow_session_not_found',
          }),
        );
        if (ending === 'expired') {
          fireEvent.click(
            screen.getByRole('button', {
              name: 'module.profileOnboarding.guided.retry',
            }),
          );
          await waitFor(() =>
            expect(result.createSession).toHaveBeenCalledTimes(2),
          );
        }
      }
      await act(async () =>
        first.onMessage({
          event_type: 'done',
          is_terminal: true,
          content: { done: false, next_turn_index: 1 },
        }),
      );
      expect(result.assistantAnswers).not.toHaveBeenCalled();
    },
  );

  test('does not offer a new import once the ordinary final summary is running', async () => {
    const result = await begin('Shared research questions', true);
    act(() =>
      result.runSession.mock.calls[0][0].onMessage({
        event_type: 'phase',
        content: { phase: 'summary' },
      }),
    );
    expect(result.runSession).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.assistant.entry',
      }),
    ).not.toBeInTheDocument();
    expect(result.assistantAnswers).not.toHaveBeenCalled();
  });

  test('requires replay of a disconnected initial run before importing early answers', async () => {
    const result = await begin('Shared research questions', true);
    enter();
    // The transport reports an uncertain outcome, so the cursor is not usable yet.
    act(() => {
      result.runSession.mock.calls[0][0].onError(new Error('Disconnected'));
    });
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.process',
      }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    );
    expect(result.runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        requestId: result.runSession.mock.calls[0][0].requestId,
        expectedTurnIndex: 0,
      }),
    );
    expect(result.assistantAnswers).not.toHaveBeenCalled();
  });

  test('hides the entry for sessions without a frozen public prompt', async () => {
    await begin('');
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.assistant.entry',
      }),
    ).not.toBeInTheDocument();
  });

  test('hides the assistant entry on mobile and reserves clearance only on larger screens', async () => {
    const result = await begin();
    const entry = screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.entry',
    });
    const markdownFlow = result.container.querySelector(
      '.profile-onboarding-markdownflow',
    );

    expect(entry).toHaveClass(
      'bottom-9',
      'hidden',
      'max-w-[calc(50%-2.75rem)]',
      'shadow-[0_6px_12px_-8px_rgba(15,23,42,0.38)]',
      'sm:inline-flex',
    );
    expect(markdownFlow).toHaveClass('py-6', 'sm:scroll-pb-20', 'sm:pb-20');
    expect(markdownFlow).not.toHaveClass('scroll-pb-20', 'pb-20');
  });

  test.each(['assistantDraft', 'onAssistantDraftChange'] as const)(
    'requires %s before offering the controlled assistant input',
    async missingProp => {
      const result = await begin();
      result.rerender(
        React.cloneElement(result.renderConversation(), {
          [missingProp]: undefined,
        }),
      );
      expect(
        screen.queryByRole('button', {
          name: 'module.profileOnboarding.assistant.entry',
        }),
      ).not.toBeInTheDocument();
      expect(screen.getByText('Question one')).toBeVisible();
      result.rerender(result.renderConversation());
      enter();
      expect(
        screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
      ).toHaveValue('External answer');
      expect(result.createSession).toHaveBeenCalledTimes(1);
    },
  );

  test('focuses the assistant introduction on entry and restores the entry on return without stealing initial focus', async () => {
    const priorFocus = document.createElement('button');
    document.body.appendChild(priorFocus);
    priorFocus.focus();
    try {
      await begin();
      expect(priorFocus).toHaveFocus();
      const entry = screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.entry',
      });
      entry.focus();
      enter();
      expect(
        screen.getByRole('heading', {
          name: 'module.profileOnboarding.assistant.title',
        }),
      ).toHaveFocus();
      expect(
        screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
      ).not.toHaveFocus();
      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.assistant.back',
        }),
      );
      expect(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.assistant.entry',
        }),
      ).toHaveFocus();
      enter();
      expect(
        screen.getByRole('heading', {
          name: 'module.profileOnboarding.assistant.title',
        }),
      ).toHaveFocus();
    } finally {
      priorFocus.remove();
    }
  });

  test('keeps the original renderer mounted when switching views and accepts nickname-only completion', async () => {
    const result = await begin();
    const question = screen.getByText('Question one');
    fireEvent.change(screen.getByLabelText('unsent question answer'), {
      target: { value: 'Unsubmitted answer' },
    });
    enter();
    expect(question).toBeInTheDocument();
    expect(question).not.toBeVisible();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.back',
      }),
    );
    expect(screen.getByText('Question one')).toBe(question);
    expect(question).toBeVisible();
    expect(screen.getByLabelText('unsent question answer')).toHaveValue(
      'Unsubmitted answer',
    );
    enter();
    process();
    expect(result.assistantAnswers).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: 'shared-session',
        expectedTurnIndex: 2,
        rawText: 'External answer',
      }),
    );
    const request = (
      result.assistantAnswers.mock.calls[0] as unknown as [
        { onMessage: (event: unknown) => void },
      ]
    )[0];
    act(() =>
      request.onMessage({
        event_type: 'done',
        is_terminal: true,
        content: {
          done: true,
          profile_draft: '',
          nickname: 'Robin',
          next_turn_index: 9,
        },
      }),
    );
    expect(result.onAssistantDraftReady).toHaveBeenCalledWith(
      '',
      'shared-session',
      'Robin',
    );
    expect(result.onDraftReady).not.toHaveBeenCalled();
    expect(result.createSession).toHaveBeenCalledTimes(1);
  });

  test('replays a disconnected delegate with the same operation, body and request ID before permitting manual answers', async () => {
    const result = await begin();
    enter();
    process();
    const first = (
      result.assistantAnswers.mock.calls[0] as unknown as [
        {
          onError: () => void;
          onMessage: (event: unknown) => void;
          requestId: string;
          rawText: string;
        },
      ]
    )[0];
    act(() => first.onError());
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.back',
      }),
    ).toBeDisabled();
    expect(
      screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
    ).toBeDisabled();
    result.rerender(result.renderConversation('A changed draft'));
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    );
    const replay = (
      result.assistantAnswers.mock.calls[1] as unknown as [typeof first]
    )[0];
    expect(replay.requestId).toBe(first.requestId);
    expect(replay.rawText).toBe('External answer');
    expect(result.runSession).toHaveBeenCalledTimes(1);
    act(() =>
      replay.onMessage({
        event_type: 'error',
        content: 'transient_markdownflow_session_busy',
      }),
    );
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.back',
      }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    );
    const finalReplay = (
      result.assistantAnswers.mock.calls[2] as unknown as [typeof first]
    )[0];
    expect(finalReplay.requestId).toBe(first.requestId);
    expect(finalReplay.rawText).toBe('External answer');

    act(() =>
      finalReplay.onMessage({
        event_type: 'done',
        is_terminal: true,
        content: { done: true, profile_draft: 'Verified profile' },
      }),
    );
    expect(result.onAssistantDraftReady).toHaveBeenCalledTimes(1);
  });

  test('recovers from actual delegate validation errors without advancing or restarting the session', async () => {
    const result = await begin();
    fireEvent.change(screen.getByLabelText('unsent question answer'), {
      target: { value: 'Keep this after an import failure' },
    });
    enter();
    process();
    const first = (
      result.assistantAnswers.mock.calls[0] as unknown as [
        { onMessage: (event: unknown) => void; requestId: string },
      ]
    )[0];
    act(() =>
      first.onMessage({
        event_type: 'error',
        content: 'transient_markdownflow_invalid',
      }),
    );
    expect(
      screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
    ).toHaveValue('External answer');
    expect(
      screen.getByLabelText('module.profileOnboarding.assistant.resultLabel'),
    ).toBeEnabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.process',
      }),
    ).toBeEnabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.guided.retry',
      }),
    ).toBeEnabled();
    expect(result.onAssistantDraftReady).not.toHaveBeenCalled();
    result.rerender(result.renderConversation('A useful answer'));
    process();
    const corrected = (
      result.assistantAnswers.mock.calls[1] as unknown as [
        {
          expectedTurnIndex: number;
          requestId: string;
          onMessage: (event: unknown) => void;
        },
      ]
    )[0];
    expect(corrected.expectedTurnIndex).toBe(2);
    expect(corrected.requestId).not.toBe(first.requestId);
    act(() =>
      corrected.onMessage({
        event_type: 'error',
        content: 'transient_markdownflow_invalid',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.back',
      }),
    );
    expect(screen.getByLabelText('unsent question answer')).toHaveValue(
      'Keep this after an import failure',
    );
    fireEvent.click(
      screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
    );
    expect(result.runSession).toHaveBeenCalledTimes(2);
    expect(result.runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({ expectedTurnIndex: 2 }),
    );
    expect(result.createSession).toHaveBeenCalledTimes(1);
  });
});
