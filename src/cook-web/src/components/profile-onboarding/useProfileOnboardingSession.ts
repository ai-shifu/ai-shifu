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
  ProfileOnboardingSessionInfo,
} from './profileOnboardingConversationModel';

type StreamHandle = { close?: () => void };

type ProfileOnboardingRunRequest = {
  expectedBlockIndex: number;
  requestId: string;
  userInput?: Record<string, string[]>;
};

type ProfileOnboardingSessionMessages = {
  retryableError: string;
  streamError: string;
  missingDraft: string;
};

type UseProfileOnboardingSessionParams = {
  createSession: () => Promise<ProfileOnboardingSessionInfo>;
  runSession: ProfileOnboardingRunSession;
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
  const sessionIdRef = React.useRef('');
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
      if (element) {
        awaitingInteractionRef.current = element.interaction;
        dispatch({ type: 'receive_item', item: element });
      }
      if (type === 'error') {
        const runtimeErrorCode = resolveRuntimeErrorCode(event.content);
        const retryable = isRetryableRuntimeError(event.content);
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
            retryable
              ? messagesRef.current.retryableError
              : messagesRef.current.streamError,
          ),
        );
        return;
      }
      if (type !== 'done' || event.is_terminal !== true) {
        return;
      }

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
        if (!draft) {
          dispatch({ type: 'fail', retryable: false });
          onErrorRef.current(new Error(messagesRef.current.missingDraft));
          return;
        }
        dispatch({ type: 'complete' });
        if (nickname) {
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
        const nextStream = runSessionRef.current({
          sessionId: sessionIdRef.current,
          expectedBlockIndex: request.expectedBlockIndex,
          requestId: request.requestId,
          userInput: request.userInput,
          onMessage: event => {
            if (runAttempt === runAttemptRef.current) {
              handleEvent(event);
            }
          },
          onError: () => {
            if (runAttempt === runAttemptRef.current) {
              handleStreamError();
            }
          },
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
    if (disabledRef.current || !streamCompletedRef.current) {
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

  const runInFlight = state.status === 'streaming';
  const loading =
    state.status === 'creating' ||
    (state.status === 'streaming' && !state.runHasContent);

  return {
    ...state,
    loading,
    runInFlight,
    retryAvailable: state.status === 'retryable_error',
    send,
    retry,
  };
};
