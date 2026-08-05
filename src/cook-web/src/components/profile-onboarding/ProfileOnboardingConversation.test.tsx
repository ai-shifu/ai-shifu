import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ProfileOnboardingConversation, {
  resolveProfileDraftFromRunEvent,
} from './ProfileOnboardingConversation';

const ANSWER_GUIDED_QUESTION_LABEL = 'answer guided question';

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
      userInput?: string;
    }>;
    onSend: (value: { variableName: string; inputText: string }) => void;
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
          onClick={() =>
            onSend({ variableName: 'profile_goal', inputText: '学会 AI' })
          }
        >
          {ANSWER_GUIDED_QUESTION_LABEL}
        </button>
      ) : null}
    </div>
  ),
}));

describe('ProfileOnboardingConversation', () => {
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

  test.each([
    'transient_markdownflow_session_not_found',
    'transient_markdownflow_invalid',
  ])('does not offer retry for non-retryable SSE error %s', async errorCode => {
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

  test('sanitizes session creation failures without offering an invalid retry', async () => {
    const onError = jest.fn();
    render(
      <ProfileOnboardingConversation
        createSession={async () => {
          throw new Error('server.profile.profileOnboardingBusy');
        }}
        runSession={jest.fn(() => ({ close: jest.fn() }))}
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
