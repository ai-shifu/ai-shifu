import React from 'react';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import type { ProfileOnboardingStreamEvent } from '@/lib/profileOnboardingSse';
import {
  initialProfileOnboardingConversationState,
  isProfileOnboardingSubmissionWithinLimits,
  isRetryableSessionCreateError,
  isRetryableRuntimeError,
  profileOnboardingConversationReducer,
  resolveNextBlockIndex,
  resolveProfileDraftFromRunEvent,
  resolveProfileNicknameFromRunEvent,
  resolveProfileOnboardingElement,
  resolveProfileOnboardingSubmission,
  resolveRuntimeErrorCode,
  resolveRunDone,
  SESSION_NOT_FOUND_RUNTIME_ERROR_CODE,
} from './profileOnboardingConversationModel';
import type {
  ProfileOnboardingRunSession,
  ProfileOnboardingAssistantAnswers,
  ProfileOnboardingSessionInfo,
} from './profileOnboardingConversationModel';

type StreamHandle = { close?: () => void };

type ProfileOnboardingRunRequest = {
  expectedBlockIndex: number;
  requestId: string;
  userInput?: Record<string, string[]>;
  rawText?: string;
};

type ProfileOnboardingSessionMessages = {
  retryableError: string;
  streamError: string;
  missingDraft: string;
  assistantError: string;
};

type UseProfileOnboardingSessionParams = {
  createSession: () => Promise<ProfileOnboardingSessionInfo>;
  runSession: ProfileOnboardingRunSession;
  assistantAnswers?: ProfileOnboardingAssistantAnswers;
  onAssistantDraftReady?: (
    draft: string,
    sessionId: string,
    nickname?: string,
  ) => void;
  disabled: boolean;
  messages: ProfileOnboardingSessionMessages;
  onSessionStarted?: (sessionId: string) => void;
  onRunInFlightChange?: (runInFlight: boolean) => void;
  onDraftReady: (
    profileDraft: string,
    sessionId: string,
    nickname?: string,
  ) => void;
  onError: (error: unknown) => void;
  onSessionCreateRejected?: (error: unknown) => void;
  onRetry?: () => void;
};

export const useProfileOnboardingSession = ({
  createSession,
  runSession,
  assistantAnswers,
  onAssistantDraftReady,
  disabled,
  messages,
  onSessionStarted,
  onRunInFlightChange,
  onDraftReady,
  onError,
  onSessionCreateRejected,
  onRetry,
}: UseProfileOnboardingSessionParams) => {
  const [state, dispatch] = React.useReducer(
    profileOnboardingConversationReducer,
    initialProfileOnboardingConversationState,
  );
  const [assistantPrompt, setAssistantPrompt] = React.useState('');
  const sessionIdRef = React.useRef('');
  const uncertainRequestRef = React.useRef(false);
  const statusRef = React.useRef(state.status);
  statusRef.current = state.status;
  const assistantAnswersRef = React.useRef(assistantAnswers);
  assistantAnswersRef.current = assistantAnswers;
  const onAssistantDraftReadyRef = React.useRef(onAssistantDraftReady);
  onAssistantDraftReadyRef.current = onAssistantDraftReady;
  const blockIndexRef = React.useRef(0);
  const requestSequenceRef = React.useRef(0);
  const streamRef = React.useRef<StreamHandle | null>(null);
  const runAttemptRef = React.useRef(0);
  const createAttemptRef = React.useRef(0);
  const initialRunPendingRef = React.useRef(false);
  const lastRunRequestRef = React.useRef<ProfileOnboardingRunRequest | null>(
    null,
  );
  const awaitingInteractionRef = React.useRef(false);
  const streamCompletedRef = React.useRef(false);
  const runtimeFailedRef = React.useRef(false);
  const mountedRef = React.useRef(true);
  const runNextRef = React.useRef<
    (userInput?: Record<string, string[]>) => void
  >(() => {});
  const createSessionRef = React.useRef(createSession);
  const runSessionRef = React.useRef(runSession);
  const onSessionStartedRef = React.useRef(onSessionStarted);
  const onRunInFlightChangeRef = React.useRef(onRunInFlightChange);
  const onDraftReadyRef = React.useRef(onDraftReady);
  const onErrorRef = React.useRef(onError);
  const onSessionCreateRejectedRef = React.useRef(onSessionCreateRejected);
  const onRetryRef = React.useRef(onRetry);
  const disabledRef = React.useRef(disabled);
  const messagesRef = React.useRef(messages);
  const runInFlightRef = React.useRef(false);
  createSessionRef.current = createSession;
  runSessionRef.current = runSession;
  onSessionStartedRef.current = onSessionStarted;
  onRunInFlightChangeRef.current = onRunInFlightChange;
  onDraftReadyRef.current = onDraftReady;
  onErrorRef.current = onError;
  onSessionCreateRejectedRef.current = onSessionCreateRejected;
  onRetryRef.current = onRetry;
  disabledRef.current = disabled;
  messagesRef.current = messages;

  const setRunInFlight = React.useCallback((runInFlight: boolean) => {
    if (runInFlightRef.current === runInFlight) {
      return;
    }
    runInFlightRef.current = runInFlight;
    onRunInFlightChangeRef.current?.(runInFlight);
  }, []);

  const stopStream = React.useCallback(() => {
    streamRef.current?.close?.();
    streamRef.current = null;
  }, []);

  const handleStreamError = React.useCallback(() => {
    if (streamCompletedRef.current || !mountedRef.current) {
      return;
    }
    uncertainRequestRef.current = true;
    runtimeFailedRef.current = true;
    streamCompletedRef.current = true;
    stopStream();
    setRunInFlight(false);
    dispatch({ type: 'fail', retryable: true });
    onErrorRef.current(new Error(messagesRef.current.retryableError));
  }, [setRunInFlight, stopStream]);

  const handleEvent = React.useCallback(
    (event: ProfileOnboardingStreamEvent) => {
      if (
        !mountedRef.current ||
        runtimeFailedRef.current ||
        streamCompletedRef.current
      ) {
        return;
      }
      const type = event.event_type || event.type || '';
      const element = resolveProfileOnboardingElement(event);
      if (element && lastRunRequestRef.current?.rawText === undefined) {
        awaitingInteractionRef.current = element.interaction;
        dispatch({ type: 'receive_item', item: element });
      }
      if (type === 'error') {
        const runtimeErrorCode = resolveRuntimeErrorCode(event.content);
        uncertainRequestRef.current =
          runtimeErrorCode === 'transient_markdownflow_session_busy';
        // Import validation runs on temporary session state, so the learner
        // can correct the paste or return to the unchanged question cursor.
        // Invalid documents in the ordinary run path remain non-retryable.
        const retryable =
          isRetryableRuntimeError(event.content) ||
          (lastRunRequestRef.current?.rawText !== undefined &&
            runtimeErrorCode === 'transient_markdownflow_invalid');
        const requiresFreshSession =
          runtimeErrorCode === SESSION_NOT_FOUND_RUNTIME_ERROR_CODE;
        runtimeFailedRef.current = true;
        streamCompletedRef.current = true;
        stopStream();
        setRunInFlight(false);
        dispatch({ type: 'fail', retryable });
        if (requiresFreshSession) {
          sessionIdRef.current = '';
          blockIndexRef.current = 0;
          lastRunRequestRef.current = null;
        }
        onErrorRef.current(
          new Error(
            lastRunRequestRef.current?.rawText !== undefined &&
              !uncertainRequestRef.current
              ? messagesRef.current.assistantError
              : retryable
                ? messagesRef.current.retryableError
                : messagesRef.current.streamError,
          ),
        );
        return;
      }
      if (type !== 'done' || event.is_terminal !== true) {
        return;
      }

      uncertainRequestRef.current = false;
      const nextBlockIndex = resolveNextBlockIndex(event);
      if (nextBlockIndex !== null) {
        blockIndexRef.current = nextBlockIndex;
      }
      streamCompletedRef.current = true;
      stopStream();
      setRunInFlight(false);
      const draft = resolveProfileDraftFromRunEvent(event);
      const nickname = resolveProfileNicknameFromRunEvent(event);
      if (resolveRunDone(event)) {
        const assistantResult =
          lastRunRequestRef.current?.rawText !== undefined;
        if (!draft && !(assistantResult && nickname)) {
          dispatch({ type: 'fail', retryable: false });
          onErrorRef.current(new Error(messagesRef.current.missingDraft));
          return;
        }
        dispatch({ type: 'complete' });
        if (assistantResult && onAssistantDraftReadyRef.current) {
          onAssistantDraftReadyRef.current(
            draft,
            sessionIdRef.current,
            nickname || undefined,
          );
        } else if (nickname) {
          onDraftReadyRef.current(draft, sessionIdRef.current, nickname);
        } else {
          onDraftReadyRef.current(draft, sessionIdRef.current);
        }
        return;
      }

      if (!awaitingInteractionRef.current) {
        queueMicrotask(() => runNextRef.current());
      } else {
        dispatch({ type: 'await_input' });
      }
    },
    [setRunInFlight, stopStream],
  );

  const runRequest = React.useCallback(
    (request: ProfileOnboardingRunRequest) => {
      if (!sessionIdRef.current || !mountedRef.current) {
        return;
      }
      stopStream();
      lastRunRequestRef.current = request;
      streamCompletedRef.current = false;
      runtimeFailedRef.current = false;
      awaitingInteractionRef.current = false;
      setRunInFlight(true);
      dispatch({ type: 'start_run' });
      const runAttempt = ++runAttemptRef.current;
      try {
        const callbacks = {
          sessionId: sessionIdRef.current,
          expectedBlockIndex: request.expectedBlockIndex,
          requestId: request.requestId,
          onMessage: (event: ProfileOnboardingStreamEvent) => {
            if (runAttempt === runAttemptRef.current) {
              handleEvent(event);
            }
          },
          onError: () => {
            if (runAttempt === runAttemptRef.current) {
              handleStreamError();
            }
          },
        };
        const nextStream =
          request.rawText !== undefined
            ? assistantAnswersRef.current!({
                ...callbacks,
                rawText: request.rawText,
              })
            : runSessionRef.current({
                ...callbacks,
                userInput: request.userInput,
              });
        if (streamCompletedRef.current) {
          nextStream.close?.();
        } else {
          streamRef.current = nextStream;
        }
      } catch {
        handleStreamError();
      }
    },
    [handleEvent, handleStreamError, setRunInFlight, stopStream],
  );

  const runNext = React.useCallback(
    (userInput?: Record<string, string[]>) => {
      runRequest({
        expectedBlockIndex: blockIndexRef.current,
        requestId: `profile-onboarding-run-${++requestSequenceRef.current}`,
        userInput,
      });
    },
    [runRequest],
  );
  runNextRef.current = runNext;

  const startSession = React.useCallback(() => {
    const createAttempt = ++createAttemptRef.current;
    ++runAttemptRef.current;
    stopStream();
    setRunInFlight(false);
    dispatch({ type: 'start_session' });
    sessionIdRef.current = '';
    setAssistantPrompt('');
    uncertainRequestRef.current = false;
    blockIndexRef.current = 0;
    lastRunRequestRef.current = null;
    awaitingInteractionRef.current = false;
    initialRunPendingRef.current = false;
    streamCompletedRef.current = false;
    runtimeFailedRef.current = false;

    void createSessionRef
      .current()
      .then(session => {
        if (createAttempt !== createAttemptRef.current || !mountedRef.current) {
          return;
        }
        sessionIdRef.current = session.session_id;
        setAssistantPrompt(session.assistant_prompt || '');
        blockIndexRef.current =
          typeof session.block_index === 'number' &&
          Number.isInteger(session.block_index) &&
          session.block_index >= 0
            ? session.block_index
            : 0;
        onSessionStartedRef.current?.(session.session_id);
        if (disabledRef.current) {
          initialRunPendingRef.current = true;
          return;
        }
        runNextRef.current();
      })
      .catch(error => {
        if (createAttempt !== createAttemptRef.current || !mountedRef.current) {
          return;
        }
        const retryable = isRetryableSessionCreateError(error);
        dispatch({ type: 'fail', retryable });
        if (!retryable && onSessionCreateRejectedRef.current) {
          onSessionCreateRejectedRef.current(error);
          return;
        }
        onErrorRef.current(
          retryable ? new Error(messagesRef.current.streamError) : error,
        );
      });
  }, [setRunInFlight, stopStream]);

  React.useEffect(() => {
    if (disabled || !initialRunPendingRef.current || !sessionIdRef.current) {
      return;
    }
    initialRunPendingRef.current = false;
    runNextRef.current();
  }, [disabled]);

  const invalidatePendingAttempts = React.useCallback(() => {
    ++createAttemptRef.current;
    ++runAttemptRef.current;
  }, []);

  React.useEffect(() => {
    mountedRef.current = true;
    startSession();
    return () => {
      mountedRef.current = false;
      initialRunPendingRef.current = false;
      invalidatePendingAttempts();
      stopStream();
      setRunInFlight(false);
    };
  }, [invalidatePendingAttempts, setRunInFlight, startSession, stopStream]);

  const send = React.useCallback((content: OnSendContentParams) => {
    if (
      disabledRef.current ||
      !streamCompletedRef.current ||
      runInFlightRef.current ||
      statusRef.current !== 'awaiting_input'
    ) {
      return;
    }
    const { values, userInput } = resolveProfileOnboardingSubmission(content);
    if (!values.length) {
      return;
    }
    const variableName = content.variableName?.trim() || 'input';
    if (!isProfileOnboardingSubmissionWithinLimits(variableName, values)) {
      dispatch({ type: 'reject_submission' });
      return;
    }
    dispatch({ type: 'accept_submission', userInput });
    runNextRef.current({ [variableName]: values });
  }, []);

  const retry = React.useCallback(() => {
    const lastRunRequest = lastRunRequestRef.current;
    if (state.status !== 'retryable_error' || disabledRef.current) {
      return;
    }
    onRetryRef.current?.();
    if (!sessionIdRef.current || !lastRunRequest) {
      startSession();
      return;
    }
    runRequest(lastRunRequest);
  }, [runRequest, startSession, state.status]);

  const submitAssistantAnswers = React.useCallback(
    (rawText: string) => {
      if (
        !assistantAnswersRef.current ||
        disabledRef.current ||
        runInFlightRef.current ||
        !sessionIdRef.current ||
        !rawText.trim() ||
        Array.from(rawText).length > 10_000 ||
        !['awaiting_input', 'retryable_error'].includes(statusRef.current)
      )
        return;
      const previous = lastRunRequestRef.current;
      if (uncertainRequestRef.current) {
        // Resolve a disconnected operation before allowing a new body or operation.
        if (previous) runRequest(previous);
        return;
      }
      onRetryRef.current?.();
      runRequest(
        previous?.rawText === rawText
          ? previous
          : {
              expectedBlockIndex: blockIndexRef.current,
              requestId: `profile-onboarding-assistant-${++requestSequenceRef.current}`,
              rawText,
            },
      );
    },
    [runRequest],
  );

  const resumeQuestions = React.useCallback(() => {
    if (runInFlightRef.current || uncertainRequestRef.current) return false;
    if (
      lastRunRequestRef.current?.rawText !== undefined &&
      statusRef.current === 'retryable_error'
    ) {
      lastRunRequestRef.current = null;
      runtimeFailedRef.current = false;
      dispatch({ type: 'resume_input' });
      onRetryRef.current?.();
    }
    return true;
  }, []);

  const runInFlight = state.status === 'streaming';
  const loading =
    state.status === 'creating' ||
    (state.status === 'streaming' && !state.runHasContent);

  return {
    ...state,
    assistantPrompt,
    submitAssistantAnswers,
    resumeQuestions,
    uncertainRequest: uncertainRequestRef.current,
    loading,
    runInFlight,
    retryAvailable: state.status === 'retryable_error',
    send,
    retry,
  };
};
