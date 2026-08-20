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
} from './ProfileOnboardingConversation';

const ANSWER_GUIDED_QUESTION_LABEL = 'answer guided question';
const DEFAULT_RENDERER_SUBMISSION: OnSendContentParams = {
  variableName: 'profile_goal',
  inputText: '学会 AI',
};
let mockRendererSubmission: OnSendContentParams = DEFAULT_RENDERER_SUBMISSION;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', resolvedLanguage: 'zh-CN' },
  }),
}));

jest.mock('markdown-flow-ui/renderer', () => ({
  MarkdownFlow: ({
    initialContentList,
    onSend,
  }: {
    initialContentList: Array<{
      content: string;
      isFinished?: boolean;
      readonly?: boolean;
      userInput?: string;
    }>;
    onSend: (value: OnSendContentParams) => void;
  }) => (
    <div>
      {initialContentList.map((item, index) => (
        <div key={`${item.content}-${index}`}>
          <span>{item.content}</span>
          {item.userInput ? <span>{item.userInput}</span> : null}
        </div>
      ))}
      {initialContentList.some(item => !item.isFinished) ? (
        <button
          type='button'
          disabled={initialContentList.some(
            item => !item.isFinished && item.readonly,
          )}
          onClick={() => onSend(mockRendererSubmission)}
        >
          {ANSWER_GUIDED_QUESTION_LABEL}
        </button>
      ) : null}
    </div>
  ),
}));

describe('ProfileOnboardingConversation', () => {
  beforeEach(() => {
    mockRendererSubmission = DEFAULT_RENDERER_SUBMISSION;
  });

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
            content: { done: false, next_block_index: 1 },
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
        expectedBlockIndex: 1,
        userInput: { profile_goal: ['Learn practical AI skills'] },
      }),
    );
    expect(
      screen.queryByText('module.profileOnboarding.guided.inputLimitError'),
    ).not.toBeInTheDocument();
  });

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
            content: { done: false, next_block_index: 1 },
          });
        });
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
    expect(screen.getByText('brief')).toBeInTheDocument();
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
            content: { done: false, next_block_index: 1 },
          });
        });
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
    expect(screen.getByText('Explain with examples')).toBeInTheDocument();
  });

  test('keeps an interaction read-only until its terminal done cursor arrives', async () => {
    let firstOnMessage: ((event: Record<string, unknown>) => void) | undefined;
    const runSession = jest.fn(({ onMessage }) => {
      firstOnMessage ??= onMessage;
      return { close: jest.fn() };
    });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-terminal-race' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(1));

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
    fireEvent.click(answerButton);
    expect(runSession).toHaveBeenCalledTimes(1);

    act(() => {
      firstOnMessage?.({
        type: 'done',
        is_terminal: true,
        content: { done: false, next_block_index: 1 },
      });
    });
    await waitFor(() => expect(answerButton).toBeEnabled());
    fireEvent.click(answerButton);
    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(2));
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        expectedBlockIndex: 1,
        userInput: { profile_goal: ['学会 AI'] },
      }),
    );
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

  test('keeps the newest guided question visible as the conversation grows', async () => {
    const scrollIntoView = jest.fn();
    const originalScrollIntoView = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      'scrollIntoView',
    );
    const originalMatchMedia = Object.getOwnPropertyDescriptor(
      window,
      'matchMedia',
    );
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    });
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: jest.fn().mockReturnValue({ matches: false }),
    });

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
            content: { done: false, next_block_index: 1 },
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
            content: { done: false, next_block_index: 2 },
          });
        });
        return { close: jest.fn() };
      });

    const view = render(
      <ProfileOnboardingConversation
        createSession={async () => ({ session_id: 'session-scroll' })}
        runSession={runSession}
        onDraftReady={jest.fn()}
        onError={jest.fn()}
      />,
    );

    try {
      await screen.findByText('?[%{{profile_goal}}...第一个问题]');
      await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
      scrollIntoView.mockClear();

      fireEvent.click(
        screen.getByRole('button', { name: ANSWER_GUIDED_QUESTION_LABEL }),
      );

      await screen.findByText('?[%{{profile_goal}}...第二个问题]');
      await waitFor(() =>
        expect(scrollIntoView).toHaveBeenCalledWith({
          block: 'nearest',
          behavior: 'smooth',
        }),
      );
    } finally {
      view.unmount();
      if (originalScrollIntoView) {
        Object.defineProperty(
          HTMLElement.prototype,
          'scrollIntoView',
          originalScrollIntoView,
        );
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView');
      }
      if (originalMatchMedia) {
        Object.defineProperty(window, 'matchMedia', originalMatchMedia);
      } else {
        Reflect.deleteProperty(window, 'matchMedia');
      }
    }
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
          expectedBlockIndex: 0,
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
        expectedBlockIndex: 0,
        requestId: expect.any(String),
        userInput: undefined,
      }),
    );
    expect(runSession.mock.calls[1][0].requestId).not.toBe(
      runSession.mock.calls[0][0].requestId,
    );
  });

  test('uses the terminal cursor and a new identity when content auto-advances', async () => {
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
            content: { done: false, next_block_index: 4 },
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
            content: { done: false, next_block_index: 5 },
          });
        });
        return { close: jest.fn() };
      });

    render(
      <ProfileOnboardingConversation
        createSession={async () => ({
          session_id: 'session-auto-next',
          block_index: 3,
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
        expectedBlockIndex: 3,
        requestId: expect.any(String),
      }),
    );
    expect(runSession.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        sessionId: 'session-auto-next',
        expectedBlockIndex: 4,
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
          content: { done: false, next_block_index: 4 },
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
    expect(onDraftReady).not.toHaveBeenCalled();
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
            content: { done: false, next_block_index: 1 },
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
        expectedBlockIndex: 1,
        requestId: expect.any(String),
        userInput: { profile_goal: ['学会 AI'] },
      }),
    );
    expect(runSession.mock.calls[2][0]).toEqual(
      expect.objectContaining({
        sessionId: 'session-retry',
        expectedBlockIndex: 1,
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
        expectedBlockIndex: 0,
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
        block_index: 2,
      })
      .mockResolvedValueOnce({
        session_id: 'fresh-session',
        block_index: 7,
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
            content: { done: false, next_block_index: 3 },
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
        expectedBlockIndex: 3,
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
        expectedBlockIndex: 7,
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
    const createSession = jest
      .fn()
      .mockRejectedValueOnce(new Error('server.profile.profileOnboardingBusy'))
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
    expect(onError.mock.calls[0][0].message).not.toContain(
      'profileOnboardingBusy',
    );
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
