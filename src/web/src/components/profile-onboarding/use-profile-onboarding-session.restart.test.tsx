import { act, renderHook, waitFor } from '@testing-library/react';
import type {
  ProfileOnboardingAssistantAnswers,
  ProfileOnboardingRunSession,
} from './profile-onboarding-conversation-model';
import { useProfileOnboardingSession } from './use-profile-onboarding-session';

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);

const renderSession = (onRewindRestart = jest.fn()) => {
  let sessionCount = 0;
  const createSession = jest.fn(async () => ({
    session_id: `profile-session-${++sessionCount}`,
  }));
  const runSession = jest.fn<
    ReturnType<ProfileOnboardingRunSession>,
    Parameters<ProfileOnboardingRunSession>
  >(() => ({ close: jest.fn() }));
  const assistantAnswers = jest.fn<
    ReturnType<ProfileOnboardingAssistantAnswers>,
    Parameters<ProfileOnboardingAssistantAnswers>
  >(() => ({ close: jest.fn() }));
  const onError = jest.fn();
  const onDraftReady = jest.fn();
  const onRewindRejected = jest.fn();
  const onRewindAnalytics = jest.fn();
  const hook = renderHook(
    ({ disabled }) =>
      useProfileOnboardingSession({
        createSession,
        runSession,
        assistantAnswers,
        disabled,
        messages: {
          retryableError: 'retry',
          streamError: 'rejected',
          missingDraft: 'missing draft',
          assistantError: 'assistant failed',
        },
        onDraftReady,
        onError,
        onRewindRejected,
        onRewindRestart,
        onRewindAnalytics,
      }),
    { initialProps: { disabled: false } },
  );
  const currentRequest = () => runSession.mock.calls.at(-1)![0];
  return {
    ...hook,
    createSession,
    runSession,
    assistantAnswers,
    currentRequest,
    onRewindRestart,
    onRewindRejected,
    onRewindAnalytics,
    onDraftReady,
    onError,
  };
};

const receiveQuestion = (
  session: ReturnType<typeof renderSession>,
  id: string,
  turnIndex: number,
) => {
  const { onMessage } = session.currentRequest();
  onMessage({
    type: 'interaction',
    content: '?[...Answer]',
    generated_block_bid: id,
    interaction_id: id,
  });
  onMessage({
    type: 'done',
    is_terminal: true,
    content: {
      done: false,
      input_accepted: turnIndex > 1,
      next_turn_index: turnIndex,
      pending_interaction_ids: [id],
      rewindable_interaction_ids: turnIndex > 1 ? ['original'] : [],
    },
  });
};

const beginEdit = async (session: ReturnType<typeof renderSession>) => {
  await waitFor(() => expect(session.runSession).toHaveBeenCalledTimes(1));
  act(() => receiveQuestion(session, 'original', 1));
  act(() =>
    session.result.current.send({ inputText: 'Original answer' }, 'original'),
  );
  act(() => receiveQuestion(session, 'current', 2));
  act(() =>
    session.result.current.send({ inputText: 'Edited answer' }, 'original'),
  );
  act(session.result.current.reGenerateConfirm.onConfirm);
  expect(session.currentRequest().rewind).toBe(true);
  return session.currentRequest();
};

const invalidRequest = {
  type: 'error',
  content: 'transient_markdownflow_invalid',
};

test('restarts an invalid rewind without old answers or queued imports and ignores late events', async () => {
  const session = renderSession();
  const editRequest = await beginEdit(session);
  act(() => session.result.current.submitAssistantAnswers('Queued old import'));
  const closeOldStream = session.runSession.mock.results[2].value.close;
  act(() => editRequest.onMessage(invalidRequest));

  await waitFor(() => expect(session.runSession).toHaveBeenCalledTimes(4));
  expect(session.createSession).toHaveBeenCalledTimes(2);
  expect(session.currentRequest()).toMatchObject({
    sessionId: 'profile-session-2',
    expectedTurnIndex: 0,
    userInput: undefined,
  });
  expect(session.currentRequest()).not.toHaveProperty('rewind');
  expect(session.currentRequest()).not.toHaveProperty('expectedInteractionId');
  expect(session.assistantAnswers).not.toHaveBeenCalled();
  expect(session.result.current.items).toEqual([]);
  expect(session.result.current.rewindableInteractionIds.size).toBe(0);
  expect(session.result.current.reGenerateConfirm.open).toBe(false);
  expect(closeOldStream).toHaveBeenCalledTimes(1);
  expect(session.onRewindRestart).toHaveBeenCalledTimes(1);
  expect(session.onError).not.toHaveBeenCalled();
  expect(session.onRewindRejected).not.toHaveBeenCalled();
  expect(session.onRewindAnalytics.mock.calls).toEqual([
    ['attempt'],
    ['failed'],
  ]);

  act(() => receiveQuestion(session, 'new-session-question', 1));
  act(() => {
    editRequest.onMessage(invalidRequest);
    editRequest.onError(new Error('Late network error'));
    editRequest.onMessage({
      type: 'content',
      content: 'Late old text',
      generated_block_bid: 'old-text',
    });
    editRequest.onMessage({
      type: 'done',
      is_terminal: true,
      content: { done: true, profile_draft: 'Late old draft' },
    });
  });
  expect(session.result.current.items.map(item => item.elementBid)).toEqual([
    'new-session-question',
  ]);
  expect(session.result.current.status).toBe('awaiting_input');
  expect(session.onDraftReady).not.toHaveBeenCalled();
  expect(session.onRewindRestart).toHaveBeenCalledTimes(1);
  expect(session.createSession).toHaveBeenCalledTimes(2);
  expect(session.onRewindAnalytics.mock.calls).toEqual([
    ['attempt'],
    ['failed'],
  ]);
});

test('restarts even when the restart notification throws', async () => {
  const onRewindRestart = jest.fn(() => {
    throw new Error('Notification unavailable');
  });
  const session = renderSession(onRewindRestart);
  const editRequest = await beginEdit(session);
  act(() => editRequest.onMessage(invalidRequest));
  await waitFor(() => expect(session.runSession).toHaveBeenCalledTimes(4));
  expect(session.currentRequest().sessionId).toBe('profile-session-2');
  expect(onRewindRestart).toHaveBeenCalledTimes(1);
});

test('creates the replacement while disabled and delays its first run until enabled', async () => {
  const session = renderSession();
  const editRequest = await beginEdit(session);
  session.rerender({ disabled: true });
  act(() => editRequest.onMessage(invalidRequest));
  await waitFor(() => expect(session.createSession).toHaveBeenCalledTimes(2));
  expect(session.runSession).toHaveBeenCalledTimes(3);
  expect(session.result.current.status).toBe('creating');
  expect(session.result.current.items).toEqual([]);
  session.rerender({ disabled: false });
  await waitFor(() => expect(session.runSession).toHaveBeenCalledTimes(4));
  expect(session.currentRequest()).toMatchObject({
    sessionId: 'profile-session-2',
    expectedTurnIndex: 0,
    userInput: undefined,
  });
  expect(session.currentRequest()).not.toHaveProperty('rewind');
  expect(session.onRewindRestart).toHaveBeenCalledTimes(1);
});

test.each([
  'transient_markdownflow_session_busy',
  'transient_markdownflow_error',
])('retries the identical edit for %s without restarting', async errorCode => {
  const session = renderSession();
  const editRequest = await beginEdit(session);
  act(() => editRequest.onMessage({ type: 'error', content: errorCode }));
  expect(session.result.current.status).toBe('retryable_error');
  expect(session.createSession).toHaveBeenCalledTimes(1);
  expect(session.onRewindRestart).not.toHaveBeenCalled();
  act(session.result.current.retry);
  expect(session.currentRequest()).toMatchObject({
    sessionId: editRequest.sessionId,
    requestId: editRequest.requestId,
    expectedTurnIndex: editRequest.expectedTurnIndex,
    expectedInteractionId: 'original',
    userInput: editRequest.userInput,
    rewind: true,
  });
});

test('retries a disconnected edit with its original request identity', async () => {
  const session = renderSession();
  const editRequest = await beginEdit(session);
  act(() => editRequest.onError(new Error('Network disconnected')));
  expect(session.result.current.status).toBe('retryable_error');
  expect(session.result.current.uncertainRequest).toBe(true);
  act(session.result.current.retry);
  expect(session.currentRequest()).toMatchObject({
    sessionId: editRequest.sessionId,
    requestId: editRequest.requestId,
    rewind: true,
  });
  expect(session.createSession).toHaveBeenCalledTimes(1);
  expect(session.onRewindRestart).not.toHaveBeenCalled();
});

test('retains a rejected edit branch when input was not accepted', async () => {
  const session = renderSession();
  const editRequest = await beginEdit(session);
  act(() =>
    editRequest.onMessage({
      type: 'done',
      is_terminal: true,
      content: {
        done: false,
        input_accepted: false,
        next_turn_index: 2,
        pending_interaction_ids: ['current'],
        rewindable_interaction_ids: ['original'],
      },
    }),
  );
  expect(session.result.current.status).toBe('awaiting_input');
  expect(session.result.current.items[0].userInput).toBe('Original answer');
  expect(session.onRewindRejected).toHaveBeenCalledTimes(1);
  expect(session.createSession).toHaveBeenCalledTimes(1);
  expect(session.onRewindRestart).not.toHaveBeenCalled();
});

test('keeps an ordinary invalid run fatal without restarting', async () => {
  const session = renderSession();
  await waitFor(() => expect(session.runSession).toHaveBeenCalledTimes(1));
  act(() => session.currentRequest().onMessage(invalidRequest));
  expect(session.result.current.status).toBe('fatal_error');
  expect(session.onError).toHaveBeenCalledTimes(1);
  expect(session.onRewindRestart).not.toHaveBeenCalled();
  expect(session.createSession).toHaveBeenCalledTimes(1);
});

test('retries invalid imported answers in the same session', async () => {
  const session = renderSession();
  await waitFor(() => expect(session.runSession).toHaveBeenCalledTimes(1));
  act(() => receiveQuestion(session, 'original', 1));
  act(() => session.result.current.submitAssistantAnswers('Imported answers'));
  const imported = session.assistantAnswers.mock.calls[0][0];
  act(() => imported.onMessage(invalidRequest));
  expect(session.result.current.status).toBe('retryable_error');
  act(session.result.current.retry);
  expect(session.assistantAnswers.mock.calls[1][0]).toMatchObject({
    sessionId: imported.sessionId,
    requestId: imported.requestId,
    expectedTurnIndex: imported.expectedTurnIndex,
    rawText: 'Imported answers',
  });
  expect(session.createSession).toHaveBeenCalledTimes(1);
  expect(session.onRewindRestart).not.toHaveBeenCalled();
});
