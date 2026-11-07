import { act, renderHook, waitFor } from '@testing-library/react';
import type {
  ProfileOnboardingAssistantAnswers,
  ProfileOnboardingRunSession,
} from './profile-onboarding-conversation-model';
import { useProfileOnboardingSession } from './use-profile-onboarding-session';

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);

test.each([false, true])(
  'runs an assistant import queued during a rejected edit after disabled=%s clears',
  async disabledDuringSettlement => {
    const createSession = async () => ({ session_id: 'profile-session' });
    const runSession = jest.fn<
      ReturnType<ProfileOnboardingRunSession>,
      Parameters<ProfileOnboardingRunSession>
    >(() => ({ close: jest.fn() }));
    const assistantAnswers = jest.fn<
      ReturnType<ProfileOnboardingAssistantAnswers>,
      Parameters<ProfileOnboardingAssistantAnswers>
    >(() => ({ close: jest.fn() }));
    const onRewindRejected = jest.fn();
    const onAssistantDraftReady = jest.fn();
    const onError = jest.fn();
    const { result, rerender } = renderHook(
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
          onDraftReady: jest.fn(),
          onAssistantDraftReady,
          onRewindRejected,
          onError,
        }),
      { initialProps: { disabled: false } },
    );
    const currentRequest = () => runSession.mock.calls.at(-1)![0];
    const receiveQuestion = (id: string, turnIndex: number) => {
      const { onMessage } = currentRequest();
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

    await waitFor(() => expect(runSession).toHaveBeenCalledTimes(1));
    act(() => receiveQuestion('original', 1));
    act(() =>
      result.current.send({ inputText: 'Original answer' }, 'original'),
    );
    act(() => receiveQuestion('current', 2));
    act(() => result.current.send({ inputText: 'Edited answer' }, 'original'));
    act(result.current.reGenerateConfirm.onConfirm);
    expect(currentRequest()).toMatchObject({
      rewind: true,
      expectedTurnIndex: 2,
      expectedInteractionId: 'original',
    });
    act(() =>
      result.current.submitAssistantAnswers('Queued assistant answers'),
    );
    expect(assistantAnswers).not.toHaveBeenCalled();

    if (disabledDuringSettlement) rerender({ disabled: true });
    await act(async () => {
      currentRequest().onMessage({
        type: 'done',
        is_terminal: true,
        content: {
          done: false,
          input_accepted: false,
          next_turn_index: 2,
          pending_interaction_ids: ['current'],
          rewindable_interaction_ids: ['original'],
        },
      });
    });
    expect(onRewindRejected).toHaveBeenCalledTimes(1);
    expect(result.current.items[0].userInput).toBe('Original answer');
    expect(onError).not.toHaveBeenCalled();
    if (disabledDuringSettlement) {
      expect(assistantAnswers).not.toHaveBeenCalled();
      rerender({ disabled: false });
    }

    await waitFor(() => expect(assistantAnswers).toHaveBeenCalledTimes(1));
    expect(assistantAnswers).toHaveBeenLastCalledWith(
      expect.objectContaining({
        sessionId: 'profile-session',
        expectedTurnIndex: 2,
        rawText: 'Queued assistant answers',
      }),
    );
    expect(runSession).toHaveBeenCalledTimes(3);
    act(() => {
      assistantAnswers.mock.calls[0][0].onMessage({
        type: 'done',
        is_terminal: true,
        content: {
          done: true,
          next_turn_index: 3,
          profile_draft: 'Imported profile',
        },
      });
    });
    expect(result.current.assistantProcessing).toBe(false);
    expect(onAssistantDraftReady).toHaveBeenCalledWith(
      'Imported profile',
      'profile-session',
      undefined,
    );
  },
);
