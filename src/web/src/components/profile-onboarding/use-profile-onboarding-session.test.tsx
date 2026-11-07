import { act, renderHook, waitFor } from '@testing-library/react';
import type { ProfileOnboardingRunSession } from './profile-onboarding-conversation-model';
import { useProfileOnboardingSession } from './use-profile-onboarding-session';

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);

const createSession = async () => ({ session_id: 'profile-session' });

const renderSession = () => {
  const runSession = jest.fn<
    ReturnType<ProfileOnboardingRunSession>,
    Parameters<ProfileOnboardingRunSession>
  >(() => ({ close: jest.fn() }));
  const onDraftReady = jest.fn();
  const onRewindAccepted = jest.fn();
  const onRewindRejected = jest.fn();
  const onRewindAnalytics = jest.fn(() => {
    throw new Error('Analytics unavailable');
  });
  const hook = renderHook(() =>
    useProfileOnboardingSession({
      createSession,
      runSession,
      disabled: false,
      messages: {
        retryableError: 'retry',
        streamError: 'rejected',
        missingDraft: 'missing draft',
        assistantError: 'assistant failed',
      },
      onDraftReady,
      onRewindAccepted,
      onRewindRejected,
      onRewindAnalytics,
      onError: jest.fn(),
    }),
  );
  const currentRequest = () => runSession.mock.calls.at(-1)![0];
  return {
    ...hook,
    runSession,
    currentRequest,
    onDraftReady,
    onRewindAccepted,
    onRewindRejected,
    onRewindAnalytics,
  };
};

const question = (id: string) => ({
  type: 'interaction',
  content: '?[...Answer]',
  generated_block_bid: id,
  interaction_id: id,
});

const completed = (draft: string, index: number) => ({
  type: 'done',
  is_terminal: true,
  content: {
    input_accepted: true,
    next_turn_index: index,
    done: true,
    profile_draft: draft,
    pending_interaction_ids: [],
    rewindable_interaction_ids: ['original-question'],
  },
});

const finishOriginalDraft = async (
  session: ReturnType<typeof renderSession>,
) => {
  await waitFor(() => expect(session.runSession).toHaveBeenCalledTimes(1));
  act(() => {
    const { onMessage } = session.currentRequest();
    onMessage(question('original-question'));
    onMessage({
      type: 'done',
      is_terminal: true,
      content: {
        done: false,
        next_turn_index: 1,
        pending_interaction_ids: ['original-question'],
      },
    });
  });
  act(() => {
    session.result.current.send(
      { inputText: 'Original answer' },
      'original-question',
    );
  });
  act(() => {
    const { onMessage } = session.currentRequest();
    onMessage({
      type: 'content',
      generated_block_bid: 'old-branch',
      content: 'Old branch',
    });
    onMessage(completed('Old draft', 2));
  });
};

test('reuses confirmed edits after transport failure and atomically replaces the old branch', async () => {
  const session = renderSession();
  await finishOriginalDraft(session);
  const edit = () =>
    session.result.current.send(
      { inputText: 'New answer' },
      'original-question',
    );

  act(edit);
  expect(session.result.current.reGenerateConfirm.open).toBe(true);
  act(session.result.current.reGenerateConfirm.onCancel);
  expect(session.runSession).toHaveBeenCalledTimes(2);
  expect(session.onRewindAnalytics).not.toHaveBeenCalled();

  act(edit);
  act(session.result.current.reGenerateConfirm.onConfirm);
  const editRequest = session.currentRequest();
  expect(editRequest).toMatchObject({
    expectedTurnIndex: 2,
    expectedInteractionId: 'original-question',
    rewind: true,
    userInput: { input: ['New answer'] },
  });
  expect(session.onRewindAnalytics.mock.calls).toEqual([['attempt']]);
  act(() => {
    editRequest.onMessage({
      type: 'rewind',
      content: { interaction_id: 'original-question' },
    });
    editRequest.onMessage(question('partial-question'));
    editRequest.onError(new Error('Network error'));
  });
  expect(session.result.current.items.map(item => item.elementBid)).toEqual([
    'original-question',
    'old-branch',
  ]);
  expect(session.onRewindAccepted).not.toHaveBeenCalled();
  expect(session.onRewindAnalytics.mock.calls).toEqual([
    ['attempt'],
    ['failed'],
  ]);

  act(session.result.current.retry);
  const retry = session.currentRequest();
  expect(retry.requestId).toBe(editRequest.requestId);
  act(() => {
    retry.onMessage({
      type: 'rewind',
      content: { interaction_id: 'original-question' },
    });
    retry.onMessage({
      type: 'content',
      generated_block_bid: 'new-branch',
      content: 'New branch',
    });
    retry.onMessage(completed('New draft', 3));
  });
  expect(session.result.current.items.map(item => item.elementBid)).toEqual([
    'original-question',
    'new-branch',
  ]);
  expect(session.result.current.items[0].userInput).toBe('New answer');
  expect(session.onRewindAccepted).toHaveBeenCalledTimes(1);
  expect(session.onDraftReady.mock.calls).toEqual([
    ['Old draft', 'profile-session'],
    ['New draft', 'profile-session'],
  ]);
  expect(session.onRewindAnalytics.mock.calls).toEqual([
    ['attempt'],
    ['failed'],
    ['attempt'],
    ['success'],
  ]);
});

test('a rejected edit preserves the previously completed question and draft', async () => {
  const session = renderSession();
  await finishOriginalDraft(session);
  act(() => {
    session.result.current.send(
      { inputText: 'Rejected answer' },
      'original-question',
    );
  });
  act(session.result.current.reGenerateConfirm.onConfirm);
  act(() => {
    const original = completed('Old draft', 2);
    session.currentRequest().onMessage({
      ...original,
      content: { ...original.content, input_accepted: false },
    });
  });
  expect(session.result.current.status).toBe('completed');
  expect(session.result.current.items[0].userInput).toBe('Original answer');
  expect(session.onRewindAccepted).not.toHaveBeenCalled();
  expect(session.onRewindRejected).toHaveBeenCalledTimes(1);
  expect(session.onDraftReady).toHaveBeenCalledTimes(1);
  expect(session.onRewindAnalytics.mock.calls).toEqual([
    ['attempt'],
    ['failed'],
  ]);
});

test('leaving during a confirmed edit emits one cancellation', async () => {
  const session = renderSession();
  await finishOriginalDraft(session);
  act(() => {
    session.result.current.send(
      { inputText: 'New answer' },
      'original-question',
    );
  });
  act(session.result.current.reGenerateConfirm.onConfirm);
  const abandoned = session.currentRequest();
  session.unmount();
  abandoned.onError(new Error('Late error'));
  expect(session.onRewindAnalytics.mock.calls).toEqual([
    ['attempt'],
    ['cancelled'],
  ]);
});

test('a terminal response without edit capabilities clears previously advertised questions', async () => {
  const session = renderSession();
  await finishOriginalDraft(session);
  expect(
    session.result.current.rewindableInteractionIds.has('original-question'),
  ).toBe(true);
  act(() => {
    session.result.current.send(
      { inputText: 'New answer' },
      'original-question',
    );
  });
  act(session.result.current.reGenerateConfirm.onConfirm);
  act(() => {
    const { onMessage } = session.currentRequest();
    onMessage({
      type: 'rewind',
      content: { interaction_id: 'original-question' },
    });
    onMessage(question('new-question'));
    onMessage({
      type: 'done',
      is_terminal: true,
      content: {
        done: false,
        input_accepted: true,
        next_turn_index: 3,
        pending_interaction_ids: ['new-question'],
      },
    });
  });
  expect(session.result.current.rewindableInteractionIds.size).toBe(0);
  expect(session.result.current.status).toBe('awaiting_input');
});
