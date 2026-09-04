'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { useTracking } from '@/c-common/hooks/useTracking';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import {
  createLiveFollowUpSession,
  encodeGeminiLiveAudioMessage,
  endLiveFollowUpSession,
  heartbeatLiveFollowUpSession,
  LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE,
  parseGeminiLiveServerMessage,
  resolveGeminiLiveWebSocketUrl,
  type LiveFollowUpLearningMode,
  type LiveFollowUpSession,
  type LiveFollowUpState,
  type LiveFollowUpSurface,
  type LiveFollowUpTranscriptRole,
} from '@/lib/liveVoiceFollowUp';

import {
  GeminiLiveTurnAccumulator,
  GEMINI_LIVE_RECONCILIATION_MS,
  type GeminiLiveTranscriptUpdate,
  type GeminiLiveTurnCommit,
} from './geminiLiveTurnAccumulator';
import {
  buildLiveVoiceFollowUpAttemptAnalytics,
  buildLiveVoiceFollowUpResultAnalytics,
  buildLiveVoiceFollowUpSessionEndAnalytics,
  buildLiveVoiceFollowUpTextAnalytics,
  buildLiveVoiceFollowUpMicrophoneAnalytics,
  LIVE_VOICE_FOLLOW_UP_TEXT_SUBMIT_EVENT,
  LIVE_VOICE_FOLLOW_UP_MICROPHONE_RESULT_EVENT,
  LIVE_VOICE_FOLLOW_UP_ATTEMPT_EVENT,
  LIVE_VOICE_FOLLOW_UP_RESULT_EVENT,
  LIVE_VOICE_FOLLOW_UP_SESSION_END_EVENT,
  shouldTrackLiveVoiceFollowUp,
  type LiveVoiceFollowUpEndReason,
  type LiveVoiceFollowUpErrorCode,
  type LiveVoiceFollowUpOutcome,
} from './liveVoiceFollowUpAnalytics';
import {
  LiveVoiceAudioUnavailableError,
  LiveVoiceFollowUpAudio,
} from './liveVoiceFollowUpAudio';
import { LiveFollowUpTurnWriter } from './liveFollowUpTurnWriter';

const SESSION_WARNING_BEFORE_EXPIRY_MS = 30_000;
const GEMINI_LIVE_SETUP_TIMEOUT_MS = 20_000;
const CREDENTIAL_RESERVATION_MARGIN_MS = 30_000;
const CAPACITY_RETRY_BACKOFF_MS = 30_000;
const MAX_INPUT_AUDIO_FRAME_BYTES = 8 * 1024;
const MAX_BUFFERED_INPUT_AUDIO_BYTES = 8 * 1024;
const MIN_HEARTBEAT_MS = 5_000;
const MAX_HEARTBEAT_MS = 30_000;

export type LiveVoiceTranscript = {
  role: LiveFollowUpTranscriptRole;
  turnIndex: number;
  text: string;
  final: boolean;
};

export type LiveVoiceFollowUpTarget = {
  anchorElementBid: string;
  surface: LiveFollowUpSurface;
};
type StartTarget = LiveVoiceFollowUpTarget;

export type LiveVoiceFollowUpHistoryTurn = {
  sessionBid: string;
  outlineBid: string;
  anchorElementBid: string;
  turnIndex: number;
  userTranscript: string;
  assistantTranscript: string;
  interrupted: boolean;
  askElementBid?: string;
  answerElementBid?: string;
};

type ActiveAttempt = StartTarget & {
  shifuBid: string;
  outlineBid: string;
  learningMode: LiveFollowUpLearningMode;
  analyticsEnabled: boolean;
  generation: number;
  attemptStartedAt: number;
  audioActivated: boolean;
  serverVoiceState: Extract<LiveFollowUpState, 'listening' | 'speaking'> | null;
  serverReadyAt: number | null;
  connectedAt: number | null;
  attemptResultReported: boolean;
  sessionEndReported: boolean;
  hadExchange: boolean;
};

const recordCompletedExchange = (
  attempt: ActiveAttempt | null,
  commits: GeminiLiveTurnCommit[],
) => {
  if (
    attempt &&
    commits.some(
      commit => commit.userTranscript && commit.playedAnswerTranscript,
    )
  ) {
    // An exchange describes locally observed conversation, not HTTP storage
    // latency or success. Usage-only and unheard responses do not count.
    attempt.hadExchange = true;
  }
};

export type LiveVoiceFollowUpViewState = {
  open: boolean;
  state: LiveFollowUpState;
  muted: boolean;
  microphonePending: boolean;
  microphoneError: LiveVoiceFollowUpErrorCode | null;
  textPending: boolean;
  anchorElementBid: string | null;
  warning: boolean;
  errorCode: LiveVoiceFollowUpErrorCode | null;
  retryable: boolean;
  retryAvailableAt: number | null;
  endReason: LiveVoiceFollowUpEndReason | null;
};

export type LiveVoiceFollowUpController = LiveVoiceFollowUpViewState & {
  start: (target: StartTarget) => void;
  startMicrophone: (target: StartTarget) => void;
  stopMicrophone: (explicit?: boolean) => void;
  sendText: (
    target: StartTarget,
    text: string,
    method: 'keyboard' | 'button',
  ) => Promise<boolean>;
  retry: () => void;
  toggleMuted: () => void;
  end: () => void;
  close: () => void;
};

type UseLiveVoiceFollowUpOptions = {
  shifuBid: string;
  outlineBid: string;
  previewMode: boolean;
  learningMode: LiveFollowUpLearningMode;
  sessionScope: LiveFollowUpLearningMode | 'classroom';
  onTurnCommitted?: (turn: LiveVoiceFollowUpHistoryTurn) => void;
  onTurnFinalized?: (turn: LiveVoiceFollowUpHistoryTurn) => void;
  onTranscript?: (
    update: LiveVoiceTranscript & {
      sessionBid: string;
      outlineBid: string;
      anchorElementBid: string;
    },
  ) => void;
  onSessionFinished?: (session: {
    sessionBid: string;
    outlineBid: string;
    anchorElementBid: string;
  }) => void;
};

type FinishAttemptOptions = {
  reason: LiveVoiceFollowUpEndReason;
  keepOpen: boolean;
  errorCode?: LiveVoiceFollowUpErrorCode | null;
  retryable?: boolean;
  pendingOutcome?: LiveVoiceFollowUpOutcome;
};

const initialState: LiveVoiceFollowUpViewState = {
  open: false,
  state: 'ended',
  muted: true,
  microphonePending: false,
  microphoneError: null,
  textPending: false,
  anchorElementBid: null,
  warning: false,
  errorCode: null,
  retryable: false,
  retryAvailableAt: null,
  endReason: null,
};

const resolveActivationErrorCode = (
  error: unknown,
): LiveVoiceFollowUpErrorCode => {
  if (error instanceof LiveVoiceAudioUnavailableError) {
    return 'audio_unavailable';
  }
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError' || error.name === 'SecurityError') {
      return 'microphone_denied';
    }
    if (
      error.name === 'NotFoundError' ||
      error.name === 'OverconstrainedError'
    ) {
      return 'microphone_unavailable';
    }
    if (error.name === 'NotReadableError' || error.name === 'AbortError') {
      return 'microphone_busy';
    }
  }
  return 'session_create_failed';
};

const sendWebSocketPayload = (websocket: WebSocket | null, payload: string) => {
  if (websocket?.readyState !== WebSocket.OPEN) {
    return false;
  }
  try {
    websocket.send(payload);
    return true;
  } catch {
    return false;
  }
};

const directSessionEndReason = (reason: LiveVoiceFollowUpEndReason) => {
  switch (reason) {
    case 'user_end':
    case 'user_close':
      return 'ended_by_user';
    case 'lesson_changed':
    case 'page_hidden':
    case 'replaced':
    case 'timeout':
      return reason;
    case 'connection_closed':
      return 'client_disconnected';
    default:
      return 'connection_error';
  }
};

export const useLiveVoiceFollowUp = ({
  shifuBid,
  outlineBid,
  previewMode,
  learningMode,
  sessionScope,
  onTurnCommitted,
  onTurnFinalized,
  onTranscript,
  onSessionFinished,
}: UseLiveVoiceFollowUpOptions): LiveVoiceFollowUpController => {
  const { trackEvent } = useTracking();
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  const [viewState, setViewState] =
    useState<LiveVoiceFollowUpViewState>(initialState);
  const attemptRef = useRef<ActiveAttempt | null>(null);
  const lastTargetRef = useRef<StartTarget | null>(null);
  const generationRef = useRef(0);
  const websocketRef = useRef<WebSocket | null>(null);
  const sessionRef = useRef<LiveFollowUpSession | null>(null);
  const admissionBlockedUntilRef = useRef(0);
  const audioRef = useRef<LiveVoiceFollowUpAudio | null>(null);
  const audioActivationAbortRef = useRef<AbortController | null>(null);
  const audioReadyRef = useRef<Promise<LiveVoiceFollowUpAudio> | null>(null);
  const microphoneAbortRef = useRef<AbortController | null>(null);
  const mutedRef = useRef(true);
  const pendingTextRef = useRef<{
    text: string;
    resolve: (sent: boolean) => void;
  } | null>(null);
  const textTransitionRef = useRef(false);
  const expectedTextResponseTurnRef = useRef<number | null>(null);
  const textTimerRef = useRef<number | null>(null);
  const flushPendingTextRef = useRef<() => void>(() => {});
  const setupReadyRef = useRef(false);
  const reconnectingRef = useRef(false);
  const resumptionHandleRef = useRef<string | null>(null);
  const outputTurnIndexRef = useRef<number | null>(null);
  const accumulatorRef = useRef<GeminiLiveTurnAccumulator | null>(null);
  const commitTimerRef = useRef<number | null>(null);
  const turnWriterRef = useRef<LiveFollowUpTurnWriter | null>(null);
  const closingFinalizersRef = useRef(new Set<() => void>());
  const finishAttemptRef = useRef<
    ((options: FinishAttemptOptions) => void) | null
  >(null);
  const warningTimerRef = useRef<number | null>(null);
  const timeoutTimerRef = useRef<number | null>(null);
  const setupTimerRef = useRef<number | null>(null);
  const heartbeatTimerRef = useRef<number | null>(null);
  const unmountedRef = useRef(false);
  const sessionScopeKey = `${shifuBid}:${outlineBid}:${sessionScope}:${previewMode ? 'preview' : 'learner'}`;
  const previousSessionScopeKeyRef = useRef(sessionScopeKey);

  const trackSafely = useCallback(
    (eventName: string, payload: Record<string, unknown>) => {
      try {
        void Promise.resolve(trackEvent(eventName, payload)).catch(() => {});
      } catch {}
    },
    [trackEvent],
  );

  const analyticsEnabled = shouldTrackLiveVoiceFollowUp({
    previewMode,
    learningMode: sessionScope,
  });

  const reportAttemptResult = useCallback(
    (
      attempt: ActiveAttempt,
      outcome: LiveVoiceFollowUpOutcome,
      errorCode: LiveVoiceFollowUpErrorCode,
    ) => {
      if (attempt.attemptResultReported) {
        return;
      }
      attempt.attemptResultReported = true;
      if (!attempt.analyticsEnabled) {
        return;
      }
      trackSafely(
        LIVE_VOICE_FOLLOW_UP_RESULT_EVENT,
        buildLiveVoiceFollowUpResultAnalytics({
          shifuBid: attempt.shifuBid,
          outlineBid: attempt.outlineBid,
          learningMode: attempt.learningMode,
          surface: attempt.surface,
          outcome,
          errorCode,
        }),
      );
    },
    [trackSafely],
  );

  const reportSessionEnd = useCallback(
    (
      attempt: ActiveAttempt,
      reason: LiveVoiceFollowUpEndReason,
      endedAt: number,
    ) => {
      if (
        attempt.sessionEndReported ||
        attempt.connectedAt === null ||
        !attempt.analyticsEnabled
      ) {
        return;
      }
      attempt.sessionEndReported = true;
      trackSafely(
        LIVE_VOICE_FOLLOW_UP_SESSION_END_EVENT,
        buildLiveVoiceFollowUpSessionEndAnalytics({
          shifuBid: attempt.shifuBid,
          outlineBid: attempt.outlineBid,
          learningMode: attempt.learningMode,
          surface: attempt.surface,
          durationMs: endedAt - attempt.connectedAt,
          hadExchange: attempt.hadExchange,
          endReason: reason,
        }),
      );
    },
    [trackSafely],
  );

  const clearTimers = useCallback(() => {
    for (const timerRef of [
      warningTimerRef,
      timeoutTimerRef,
      setupTimerRef,
      heartbeatTimerRef,
      commitTimerRef,
    ]) {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, []);

  const applyTranscriptUpdates = useCallback(
    (updates: GeminiLiveTranscriptUpdate[]) => {
      if (!updates.length) {
        return;
      }
      for (const update of updates) {
        const attempt = attemptRef.current;
        const session = sessionRef.current;
        if (attempt && session) {
          onTranscript?.({
            ...update,
            sessionBid: session.session_bid,
            outlineBid: attempt.outlineBid,
            anchorElementBid: attempt.anchorElementBid,
          });
        }
      }
    },
    [onTranscript],
  );

  const getTurnWriter = useCallback(
    (
      sessionBid: string,
      outlineBid: string,
      anchorElementBid: string,
      generation: number,
    ) => {
      if (turnWriterRef.current?.sessionBid === sessionBid) {
        return turnWriterRef.current;
      }
      const writer = new LiveFollowUpTurnWriter(
        sessionBid,
        (commit, acknowledgement) => {
          try {
            onTurnCommitted?.({
              outlineBid,
              anchorElementBid,
              sessionBid,
              turnIndex: commit.turnIndex,
              userTranscript: commit.userTranscript,
              assistantTranscript: commit.playedAnswerTranscript,
              interrupted: commit.interrupted,
              askElementBid: acknowledgement?.ask_element_bid,
              answerElementBid: acknowledgement?.answer_element_bid,
            });
          } catch {}
        },
        () => {
          if (attemptRef.current?.generation === generation) {
            finishAttemptRef.current?.({
              reason: 'connection_error',
              keepOpen: true,
              errorCode: 'server_error',
              retryable: true,
              pendingOutcome: 'failed',
            });
          }
        },
      );
      turnWriterRef.current = writer;
      return writer;
    },
    [onTurnCommitted],
  );

  const persistCommits = useCallback(
    (
      sessionBid: string,
      outlineBid: string,
      anchorElementBid: string,
      commits: GeminiLiveTurnCommit[],
      generation: number,
    ) => {
      try {
        commits.forEach(commit =>
          onTurnFinalized?.({
            sessionBid,
            outlineBid,
            anchorElementBid,
            turnIndex: commit.turnIndex,
            userTranscript: commit.userTranscript,
            assistantTranscript: commit.playedAnswerTranscript,
            interrupted: commit.interrupted,
          }),
        );
        getTurnWriter(
          sessionBid,
          outlineBid,
          anchorElementBid,
          generation,
        ).enqueue(commits);
      } catch {
        finishAttemptRef.current?.({
          reason: 'connection_error',
          keepOpen: true,
          errorCode: 'server_error',
          retryable: true,
          pendingOutcome: 'failed',
        });
      }
    },
    [getTurnWriter, onTurnFinalized],
  );

  const flushReadyCommits = useCallback(
    (generation: number, force = false) => {
      const attempt = attemptRef.current;
      const session = sessionRef.current;
      const accumulator = accumulatorRef.current;
      if (
        !attempt ||
        attempt.generation !== generation ||
        !session ||
        !accumulator
      ) {
        return;
      }
      const commits = force
        ? accumulator.finishSession()
        : accumulator.popReady();
      recordCompletedExchange(attempt, commits);
      persistCommits(
        session.session_bid,
        attempt.outlineBid,
        attempt.anchorElementBid,
        commits,
        generation,
      );
    },
    [persistCommits],
  );

  const scheduleCommitFlush = useCallback(
    (generation: number) => {
      if (commitTimerRef.current !== null) {
        window.clearTimeout(commitTimerRef.current);
      }
      const readyAt = Date.now() + GEMINI_LIVE_RECONCILIATION_MS;
      const flushAfterReconciliation = () => {
        if (attemptRef.current?.generation !== generation) {
          return;
        }
        // Timer scheduling and Date.now can differ by a clock tick. A slightly
        // early callback must not strand a terminal turn without another flush.
        const remainingMs = readyAt - Date.now();
        if (remainingMs > 0) {
          commitTimerRef.current = window.setTimeout(
            flushAfterReconciliation,
            remainingMs,
          );
          return;
        }
        commitTimerRef.current = null;
        flushReadyCommits(generation);
      };
      commitTimerRef.current = window.setTimeout(
        flushAfterReconciliation,
        GEMINI_LIVE_RECONCILIATION_MS,
      );
    },
    [flushReadyCommits],
  );

  const teardownTransport = useCallback(
    (reason: LiveVoiceFollowUpEndReason) => {
      const endedAt = Date.now();
      clearTimers();
      if (textTimerRef.current !== null)
        window.clearTimeout(textTimerRef.current);
      textTimerRef.current = null;
      textTransitionRef.current = false;
      expectedTextResponseTurnRef.current = null;
      pendingTextRef.current?.resolve(false);
      pendingTextRef.current = null;
      microphoneAbortRef.current?.abort();
      microphoneAbortRef.current = null;
      mutedRef.current = true;
      audioReadyRef.current = null;
      audioActivationAbortRef.current?.abort();
      audioActivationAbortRef.current = null;
      setupReadyRef.current = false;
      reconnectingRef.current = false;
      resumptionHandleRef.current = null;
      outputTurnIndexRef.current = null;

      const websocket = websocketRef.current;
      websocketRef.current = null;
      if (websocket) {
        websocket.onopen = null;
        websocket.onmessage = null;
        websocket.onerror = null;
        websocket.onclose = null;
        if (
          websocket.readyState === WebSocket.OPEN ||
          websocket.readyState === WebSocket.CONNECTING
        ) {
          websocket.close(1000, 'session ended');
        }
      }

      const attempt = attemptRef.current;
      const session = sessionRef.current;
      const accumulator = accumulatorRef.current;
      sessionRef.current = null;
      accumulatorRef.current = null;
      const audio = audioRef.current;
      audioRef.current = null;

      const writer =
        attempt && session
          ? getTurnWriter(
              session.session_bid,
              attempt.outlineBid,
              attempt.anchorElementBid,
              attempt.generation,
            )
          : null;
      turnWriterRef.current = null;
      const endReason = directSessionEndReason(reason);
      const publishFinal = (commits: GeminiLiveTurnCommit[]) => {
        if (!attempt || !session) return;
        commits.forEach(commit =>
          onTurnFinalized?.({
            sessionBid: session.session_bid,
            outlineBid: attempt.outlineBid,
            anchorElementBid: attempt.anchorElementBid,
            turnIndex: commit.turnIndex,
            userTranscript: commit.userTranscript,
            assistantTranscript: commit.playedAnswerTranscript,
            interrupted: commit.interrupted,
          }),
        );
        onSessionFinished?.({
          sessionBid: session.session_bid,
          outlineBid: attempt.outlineBid,
          anchorElementBid: attempt.anchorElementBid,
        });
      };
      const flushForUnload = () => {
        try {
          const commits = accumulator?.finishSession() ?? [];
          publishFinal(commits);
          recordCompletedExchange(attempt, commits);
          void writer?.handOffForUnload(commits, endReason).catch(() => {});
        } catch {
        } finally {
          if (attempt) {
            reportSessionEnd(attempt, reason, endedAt);
          }
        }
      };
      closingFinalizersRef.current.add(flushForUnload);
      // stop() synchronously releases the microphone and then requests the
      // worklet's final playback watermark. Only unload cannot await that ACK.
      const stoppedAudio = audio?.stop().catch(() => {});
      if (reason === 'page_hidden' || unmountedRef.current) {
        flushForUnload();
      }
      const finalize = async () => {
        await stoppedAudio;
        if (
          !attemptRef.current ||
          attemptRef.current.generation === attempt?.generation
        ) {
          releaseExclusive();
        }
        try {
          const commits = accumulator?.finishSession() ?? [];
          publishFinal(commits);
          recordCompletedExchange(attempt, commits);
          if (attempt) {
            reportSessionEnd(attempt, reason, endedAt);
          }
          writer?.enqueue(commits);
          await writer?.finish(endReason);
        } catch {
        } finally {
          if (attempt) {
            reportSessionEnd(attempt, reason, endedAt);
          }
          closingFinalizersRef.current.delete(flushForUnload);
        }
      };
      void finalize();
    },
    [
      clearTimers,
      getTurnWriter,
      releaseExclusive,
      reportSessionEnd,
      onTurnFinalized,
      onSessionFinished,
    ],
  );

  const finishAttempt = useCallback(
    ({
      reason,
      keepOpen,
      errorCode = null,
      retryable = false,
      pendingOutcome = 'cancelled',
    }: FinishAttemptOptions) => {
      const attempt = attemptRef.current;
      teardownTransport(reason);
      if (attempt) {
        if (!attempt.attemptResultReported) {
          reportAttemptResult(attempt, pendingOutcome, errorCode || 'none');
        }
      }
      attemptRef.current = null;
      if (!unmountedRef.current) {
        const retryAvailableAt =
          retryable && admissionBlockedUntilRef.current > Date.now()
            ? admissionBlockedUntilRef.current
            : null;
        setViewState(previous => ({
          ...previous,
          open: keepOpen,
          state: 'ended',
          muted: true,
          microphonePending: false,
          textPending: false,
          warning: false,
          errorCode,
          retryable: retryable && retryAvailableAt === null,
          retryAvailableAt,
          endReason: reason,
        }));
      }
    },
    [reportAttemptResult, teardownTransport],
  );
  finishAttemptRef.current = finishAttempt;

  const start = useCallback(
    ({ anchorElementBid, surface }: StartTarget) => {
      const normalizedAnchor = anchorElementBid.trim();
      if (!normalizedAnchor || !shifuBid || !outlineBid) {
        return false;
      }
      if (sessionScope === 'classroom') return false;
      if (attemptRef.current) {
        return attemptRef.current.anchorElementBid === normalizedAnchor;
      }
      if (admissionBlockedUntilRef.current > Date.now()) {
        lastTargetRef.current = { anchorElementBid: normalizedAnchor, surface };
        setViewState(previous => ({
          ...previous,
          open: true,
          anchorElementBid: normalizedAnchor,
          state: 'ended',
          retryable: false,
          retryAvailableAt: admissionBlockedUntilRef.current,
          errorCode: 'capacity_exceeded',
        }));
        return false;
      }
      const generation = ++generationRef.current;
      const target = { anchorElementBid: normalizedAnchor, surface };
      lastTargetRef.current = target;
      const attempt: ActiveAttempt = {
        ...target,
        shifuBid,
        outlineBid,
        learningMode,
        analyticsEnabled,
        generation,
        attemptStartedAt: Date.now(),
        audioActivated: false,
        serverVoiceState: null,
        serverReadyAt: null,
        connectedAt: null,
        attemptResultReported: false,
        sessionEndReported: false,
        hadExchange: false,
      };
      attemptRef.current = attempt;
      mutedRef.current = true;
      setupReadyRef.current = false;
      const attemptAccumulator = new GeminiLiveTurnAccumulator();
      accumulatorRef.current = attemptAccumulator;

      if (analyticsEnabled) {
        trackSafely(
          LIVE_VOICE_FOLLOW_UP_ATTEMPT_EVENT,
          buildLiveVoiceFollowUpAttemptAnalytics({
            shifuBid,
            outlineBid,
            learningMode,
            surface,
          }),
        );
      }
      setViewState({
        ...initialState,
        open: true,
        state: 'connecting',
        anchorElementBid: normalizedAnchor,
      });
      requestExclusive(() => {
        finishAttempt({ reason: 'replaced', keepOpen: false });
      });

      const markConnectedIfReady = () => {
        const currentAttempt = attemptRef.current;
        if (
          currentAttempt?.generation !== generation ||
          !setupReadyRef.current ||
          !currentAttempt.audioActivated ||
          currentAttempt.serverVoiceState === null
        ) {
          return;
        }
        if (setupTimerRef.current !== null) {
          window.clearTimeout(setupTimerRef.current);
          setupTimerRef.current = null;
        }
        // Resumption also waits for setup, but must not emit another result.
        if (currentAttempt.connectedAt !== null) {
          flushPendingTextRef.current();
          return;
        }
        currentAttempt.connectedAt = Date.now();
        reportAttemptResult(currentAttempt, 'success', 'none');
        setViewState(previous => ({
          ...previous,
          state: currentAttempt.serverVoiceState || 'listening',
        }));
        flushPendingTextRef.current();
      };

      const startSessionTimers = (
        currentAttempt: ActiveAttempt,
        expiresAt: string,
      ) => {
        if (currentAttempt.serverReadyAt !== null) {
          return true;
        }
        const now = Date.now();
        const expiresAtMs = Date.parse(expiresAt);
        const remainingMs = expiresAtMs - now;
        if (!Number.isFinite(expiresAtMs) || remainingMs <= 0) {
          finishAttempt({
            reason: 'timeout',
            keepOpen: true,
            retryable: true,
            errorCode: 'server_error',
            pendingOutcome: 'failed',
          });
          return false;
        }
        currentAttempt.serverReadyAt = now;
        warningTimerRef.current = window.setTimeout(
          () => {
            setViewState(previous => ({ ...previous, warning: true }));
          },
          Math.max(0, remainingMs - SESSION_WARNING_BEFORE_EXPIRY_MS),
        );
        timeoutTimerRef.current = window.setTimeout(() => {
          const timedOutAttempt = attemptRef.current;
          const endedBeforeConnection =
            timedOutAttempt?.generation === generation &&
            timedOutAttempt.connectedAt === null;
          finishAttempt({
            reason: 'timeout',
            keepOpen: true,
            retryable: true,
            errorCode: endedBeforeConnection ? 'server_error' : null,
            pendingOutcome: endedBeforeConnection ? 'failed' : 'cancelled',
          });
        }, remainingMs);
        return true;
      };

      const audioActivationAbort = new AbortController();
      audioActivationAbortRef.current = audioActivationAbort;
      const activateAudio = () =>
        LiveVoiceFollowUpAudio.activate(
          {
            onInputFrame: frame => {
              const currentAttempt = attemptRef.current;
              const websocket = websocketRef.current;
              if (
                currentAttempt?.generation !== generation ||
                mutedRef.current ||
                !setupReadyRef.current ||
                websocket?.readyState !== WebSocket.OPEN ||
                frame.byteLength > MAX_INPUT_AUDIO_FRAME_BYTES ||
                websocket.bufferedAmount + frame.byteLength * 2 >
                  MAX_BUFFERED_INPUT_AUDIO_BYTES
              ) {
                return;
              }
              sendWebSocketPayload(
                websocket,
                encodeGeminiLiveAudioMessage(frame),
              );
            },
            onPlaybackProgress: (turnIndex, playedBytes) => {
              attemptAccumulator.recordPlaybackProgress(turnIndex, playedBytes);
              flushReadyCommits(generation);
            },
            onPlaybackComplete: turnIndex => {
              attemptAccumulator.markPlaybackComplete(turnIndex);
              flushReadyCommits(generation);
              if (outputTurnIndexRef.current === turnIndex) {
                outputTurnIndexRef.current = null;
                const currentAttempt = attemptRef.current;
                if (currentAttempt?.generation === generation) {
                  currentAttempt.serverVoiceState = 'listening';
                  setViewState(previous => ({
                    ...previous,
                    state: 'listening',
                  }));
                }
              }
            },
          },
          audioActivationAbort.signal,
        );

      let audioPromise: Promise<LiveVoiceFollowUpAudio>;
      try {
        audioPromise = activateAudio();
      } catch (error) {
        audioPromise = Promise.reject(error);
      }
      audioReadyRef.current = audioPromise;
      void audioPromise
        .then(audio => {
          if (audioActivationAbortRef.current === audioActivationAbort) {
            audioActivationAbortRef.current = null;
          }
          if (attemptRef.current?.generation !== generation) {
            void audio.stop().catch(() => {});
            return;
          }
          audioRef.current = audio;
          audio.setMuted(mutedRef.current);
          attemptRef.current.audioActivated = true;
          markConnectedIfReady();
        })
        .catch(error => {
          if (attemptRef.current?.generation === generation) {
            finishAttempt({
              reason: 'connection_error',
              keepOpen: true,
              errorCode: resolveActivationErrorCode(error),
              retryable: true,
              pendingOutcome: 'failed',
            });
          }
        });

      const armConnectionTimeout = (provisioning = false) => {
        if (setupTimerRef.current !== null) {
          window.clearTimeout(setupTimerRef.current);
        }
        setupTimerRef.current = window.setTimeout(() => {
          setupTimerRef.current = null;
          const currentAttempt = attemptRef.current;
          if (
            currentAttempt?.generation !== generation ||
            (setupReadyRef.current && currentAttempt.audioActivated)
          ) {
            return;
          }
          if (provisioning) {
            // A stalled response may already own server capacity. Back off
            // retries; a late response still records its actual expiry below.
            admissionBlockedUntilRef.current = Math.max(
              admissionBlockedUntilRef.current,
              Date.now() + CAPACITY_RETRY_BACKOFF_MS,
            );
          }
          finishAttempt({
            reason: 'connection_error',
            keepOpen: true,
            errorCode: 'network_error',
            retryable: true,
            pendingOutcome: 'failed',
          });
        }, GEMINI_LIVE_SETUP_TIMEOUT_MS);
      };

      armConnectionTimeout(true);
      let sessionPromise: ReturnType<typeof createLiveFollowUpSession>;
      try {
        sessionPromise = createLiveFollowUpSession(shifuBid, outlineBid, {
          anchor_element_bid: normalizedAnchor,
          preview_mode: previewMode,
          learning_mode: learningMode,
          surface,
        });
      } catch (error) {
        sessionPromise = Promise.reject(error);
      }

      const openGeminiSocket = (
        session: LiveFollowUpSession,
        resumptionHandle: string | null,
      ) => {
        const previous = websocketRef.current;
        if (previous) {
          previous.onopen = null;
          previous.onmessage = null;
          previous.onerror = null;
          previous.onclose = null;
          if (
            previous.readyState === WebSocket.OPEN ||
            previous.readyState === WebSocket.CONNECTING
          ) {
            previous.close(1000, 'session resuming');
          }
        }
        setupReadyRef.current = false;
        armConnectionTimeout();
        const websocket = new WebSocket(
          resolveGeminiLiveWebSocketUrl(
            session.websocket_url,
            session.ephemeral_token,
          ),
        );
        // Gemini sends binary JSON; decode it synchronously to preserve event order.
        websocket.binaryType = 'arraybuffer';
        websocketRef.current = websocket;

        websocket.onopen = () => {
          if (attemptRef.current?.generation !== generation) {
            websocket.close();
            return;
          }
          const setup = {
            setup: {
              ...session.setup.setup,
              sessionResumption: resumptionHandle
                ? { handle: resumptionHandle }
                : {},
              ...(resumptionHandle ? { historyConfig: undefined } : {}),
            },
          };
          sendWebSocketPayload(websocket, JSON.stringify(setup));
        };

        websocket.onmessage = event => {
          if (
            attemptRef.current?.generation !== generation ||
            (typeof event.data !== 'string' &&
              !(event.data instanceof ArrayBuffer))
          ) {
            return;
          }
          const message = parseGeminiLiveServerMessage(event.data);
          if (!message) {
            return;
          }
          if (message.upstreamError) {
            finishAttempt({
              reason: 'connection_error',
              keepOpen: true,
              errorCode: 'server_error',
              retryable: true,
              pendingOutcome: 'failed',
            });
            return;
          }
          if (message.resumable === false) {
            resumptionHandleRef.current = null;
          } else if (message.resumptionHandle) {
            resumptionHandleRef.current = message.resumptionHandle;
          }
          if (message.setupComplete) {
            if (!resumptionHandle && session.history) {
              sendWebSocketPayload(websocket, JSON.stringify(session.history));
            }
            setupReadyRef.current = true;
            reconnectingRef.current = false;
            const currentAttempt = attemptRef.current;
            if (currentAttempt?.generation === generation) {
              currentAttempt.serverVoiceState = 'listening';
              if (!startSessionTimers(currentAttempt, session.expires_at)) {
                return;
              }
              markConnectedIfReady();
            }
            setViewState(previousState => ({
              ...previousState,
              state:
                attemptRef.current?.connectedAt === null
                  ? 'connecting'
                  : 'listening',
            }));
          }

          const ingest = attemptAccumulator.process(message);
          applyTranscriptUpdates(ingest.transcriptUpdates);
          if (
            ingest.audioTurnIndex !== null &&
            !attemptAccumulator.suppressPlayback(ingest.audioTurnIndex)
          ) {
            outputTurnIndexRef.current = ingest.audioTurnIndex;
            for (const chunk of ingest.audioChunks) {
              audioRef.current?.enqueueOutput(chunk, ingest.audioTurnIndex);
            }
            const currentAttempt = attemptRef.current;
            if (currentAttempt?.generation === generation) {
              currentAttempt.serverVoiceState = 'speaking';
              if (currentAttempt.connectedAt !== null) {
                setViewState(previousState => ({
                  ...previousState,
                  state: 'speaking',
                }));
              }
            }
          }
          if (ingest.interruptedTurnIndex !== null) {
            audioRef.current?.clearPlayback();
            outputTurnIndexRef.current = null;
            const currentAttempt = attemptRef.current;
            if (currentAttempt?.generation === generation) {
              currentAttempt.serverVoiceState = 'listening';
              setViewState(previousState => ({
                ...previousState,
                state: 'listening',
              }));
            }
          }
          if (ingest.terminalTurnIndex !== null) {
            if (ingest.terminalTurnIndex !== ingest.interruptedTurnIndex) {
              audioRef.current?.finishOutput(ingest.terminalTurnIndex);
            }
            scheduleCommitFlush(generation);
          }
          if (
            expectedTextResponseTurnRef.current !== null &&
            !attemptAccumulator.textHandoffPending &&
            ((ingest.audioTurnIndex ?? 0) >=
              expectedTextResponseTurnRef.current ||
              (ingest.terminalTurnIndex ?? 0) >=
                expectedTextResponseTurnRef.current)
          ) {
            // An old coalesced interruption/completion is not acknowledgement
            // of the pending question. Wait for activity in its own turn.
            textTransitionRef.current = false;
            expectedTextResponseTurnRef.current = null;
            if (textTimerRef.current !== null)
              window.clearTimeout(textTimerRef.current);
            textTimerRef.current = null;
            setViewState(previous => ({ ...previous, textPending: false }));
          }

          if (message.goAway) {
            const handle = resumptionHandleRef.current;
            if (!handle) {
              finishAttempt({
                reason: 'connection_error',
                keepOpen: true,
                errorCode: 'network_error',
                retryable: true,
                pendingOutcome: 'failed',
              });
              return;
            }
            reconnectingRef.current = true;
            const currentAttempt = attemptRef.current;
            if (currentAttempt?.generation === generation) {
              currentAttempt.serverVoiceState = null;
            }
            setViewState(previousState => ({
              ...previousState,
              state: 'reconnecting',
            }));
            openGeminiSocket(session, handle);
          }
        };

        websocket.onerror = () => {
          if (attemptRef.current?.generation !== generation) {
            return;
          }
          finishAttempt({
            reason: 'connection_error',
            keepOpen: true,
            errorCode: 'websocket_failed',
            retryable: true,
            pendingOutcome: 'failed',
          });
        };
        websocket.onclose = () => {
          if (attemptRef.current?.generation !== generation) {
            return;
          }
          finishAttempt({
            reason: 'connection_closed',
            keepOpen: true,
            errorCode: 'network_error',
            retryable: true,
            pendingOutcome: 'failed',
          });
        };
      };

      void sessionPromise
        .then(session => {
          const expiresAt = Date.parse(session.expires_at);
          if (Number.isFinite(expiresAt)) {
            admissionBlockedUntilRef.current = Math.max(
              admissionBlockedUntilRef.current,
              expiresAt + CREDENTIAL_RESERVATION_MARGIN_MS,
            );
          }
          if (attemptRef.current?.generation !== generation) {
            if (!unmountedRef.current) {
              setViewState(previous =>
                previous.open && previous.state === 'ended'
                  ? {
                      ...previous,
                      retryable: false,
                      retryAvailableAt: admissionBlockedUntilRef.current,
                    }
                  : previous,
              );
            }
            void endLiveFollowUpSession(
              session.session_bid,
              'client_disconnected',
            ).catch(() => {});
            return;
          }
          sessionRef.current = session;
          openGeminiSocket(session, null);
          const heartbeatMs = Math.min(
            MAX_HEARTBEAT_MS,
            Math.max(MIN_HEARTBEAT_MS, session.heartbeat_interval_ms),
          );
          heartbeatTimerRef.current = window.setInterval(() => {
            if (attemptRef.current?.generation !== generation) {
              return;
            }
            void heartbeatLiveFollowUpSession(session.session_bid).catch(() => {
              if (attemptRef.current?.generation === generation) {
                finishAttempt({
                  reason: 'connection_error',
                  keepOpen: true,
                  errorCode: 'server_error',
                  retryable: true,
                  pendingOutcome: 'failed',
                });
              }
            });
          }, heartbeatMs);
        })
        .catch(error => {
          if (attemptRef.current?.generation === generation) {
            const capacityExceeded =
              typeof error === 'object' &&
              error !== null &&
              'code' in error &&
              error.code === LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE;
            if (capacityExceeded) {
              // Another tab/user may own admission. The expiry is unknown, so
              // throttle explicit retries without promising available capacity.
              admissionBlockedUntilRef.current = Math.max(
                admissionBlockedUntilRef.current,
                Date.now() + CAPACITY_RETRY_BACKOFF_MS,
              );
            }
            finishAttempt({
              reason: 'connection_error',
              keepOpen: true,
              errorCode: capacityExceeded
                ? 'capacity_exceeded'
                : 'session_create_failed',
              retryable: true,
              pendingOutcome: 'failed',
            });
          }
        });
      return true;
    },
    [
      analyticsEnabled,
      applyTranscriptUpdates,
      finishAttempt,
      flushReadyCommits,
      learningMode,
      outlineBid,
      previewMode,
      reportAttemptResult,
      requestExclusive,
      scheduleCommitFlush,
      shifuBid,
      sessionScope,
      trackSafely,
    ],
  );

  const stopMicrophone = useCallback(
    (explicit = false) => {
      const wasEnabled = !mutedRef.current;
      const attempt = attemptRef.current;
      microphoneAbortRef.current?.abort();
      microphoneAbortRef.current = null;
      mutedRef.current = true;
      audioRef.current?.stopMicrophone();
      if (wasEnabled) {
        sendWebSocketPayload(
          websocketRef.current,
          JSON.stringify({ realtimeInput: { audioStreamEnd: true } }),
        );
      }
      setViewState(previous => ({
        ...previous,
        muted: true,
        microphonePending: false,
      }));
      if (explicit && wasEnabled && attempt?.analyticsEnabled) {
        trackSafely(
          LIVE_VOICE_FOLLOW_UP_MICROPHONE_RESULT_EVENT,
          buildLiveVoiceFollowUpMicrophoneAnalytics({
            ...attempt,
            enabled: false,
            outcome: 'success',
            errorCode: 'none',
          }),
        );
      }
    },
    [trackSafely],
  );

  const startMicrophone = useCallback(
    (target: StartTarget) => {
      if (
        microphoneAbortRef.current ||
        !mutedRef.current ||
        textTransitionRef.current ||
        !start(target)
      )
        return;
      const attempt = attemptRef.current!;
      const abort = new AbortController();
      microphoneAbortRef.current = abort;
      setViewState(previous => ({
        ...previous,
        microphonePending: true,
        microphoneError: null,
      }));
      let capture: Promise<MediaStream>;
      try {
        capture = LiveVoiceFollowUpAudio.requestMicrophone(abort.signal);
      } catch (error) {
        capture = Promise.reject(error);
      }
      const report = (
        outcome: LiveVoiceFollowUpOutcome,
        errorCode: LiveVoiceFollowUpErrorCode,
      ) => {
        if (attempt.analyticsEnabled)
          trackSafely(
            LIVE_VOICE_FOLLOW_UP_MICROPHONE_RESULT_EVENT,
            buildLiveVoiceFollowUpMicrophoneAnalytics({
              ...attempt,
              enabled: true,
              outcome,
              errorCode,
            }),
          );
      };
      const ready = audioReadyRef.current;
      void capture
        .then(async stream => {
          const release = () =>
            stream.getTracks().forEach(track => track.stop());
          abort.signal.addEventListener('abort', release, { once: true });
          try {
            if (abort.signal.aborted)
              throw new DOMException('Microphone cancelled', 'AbortError');
            const audio = await ready;
            if (
              abort.signal.aborted ||
              attemptRef.current !== attempt ||
              !audio
            ) {
              throw new DOMException('Microphone cancelled', 'AbortError');
            }
            audio.attachMicrophone(stream);
            mutedRef.current = false;
            setViewState(previous => ({
              ...previous,
              muted: false,
              microphonePending: false,
            }));
            report('success', 'none');
          } catch (error) {
            release();
            throw error;
          } finally {
            abort.signal.removeEventListener('abort', release);
          }
        })
        .catch(error => {
          const cancelled = abort.signal.aborted;
          const errorCode = cancelled
            ? 'none'
            : resolveActivationErrorCode(error);
          report(cancelled ? 'cancelled' : 'failed', errorCode);
          if (attemptRef.current === attempt && !cancelled) {
            setViewState(previous => ({
              ...previous,
              muted: true,
              microphonePending: false,
              microphoneError: errorCode,
            }));
          }
        })
        .finally(() => {
          if (microphoneAbortRef.current === abort)
            microphoneAbortRef.current = null;
        });
    },
    [start, trackSafely],
  );

  const flushPendingText = useCallback(() => {
    const pending = pendingTextRef.current;
    const attempt = attemptRef.current;
    const accumulator = accumulatorRef.current;
    if (
      !pending ||
      !attempt ||
      !accumulator ||
      !setupReadyRef.current ||
      !attempt.audioActivated
    )
      return;
    const websocket = websocketRef.current;
    if (
      !websocket ||
      websocket.bufferedAmount > MAX_BUFFERED_INPUT_AUDIO_BYTES ||
      !sendWebSocketPayload(
        websocket,
        JSON.stringify({ realtimeInput: { text: pending.text } }),
      )
    ) {
      finishAttempt({
        reason: 'connection_error',
        keepOpen: true,
        errorCode: 'network_error',
        retryable: true,
        pendingOutcome: 'failed',
      });
      return;
    }
    // WebSocket send is synchronous; register before any provider message can run.
    const submitted = accumulator.submitText(pending.text);
    pendingTextRef.current = null;
    if (!submitted) {
      pending.resolve(false);
      return;
    }
    expectedTextResponseTurnRef.current = submitted.update.turnIndex;
    applyTranscriptUpdates([submitted.update]);
    if (submitted.interruptedTurnIndex !== null) {
      outputTurnIndexRef.current = null;
      void audioRef.current
        ?.interruptPlayback()
        .then(() => flushReadyCommits(attempt.generation))
        .catch(() => {});
    }
    pending.resolve(true);
    textTimerRef.current = window.setTimeout(() => {
      if (attemptRef.current === attempt && textTransitionRef.current) {
        finishAttempt({
          reason: 'connection_error',
          keepOpen: true,
          errorCode: 'server_error',
          retryable: true,
        });
      }
    }, GEMINI_LIVE_SETUP_TIMEOUT_MS);
  }, [applyTranscriptUpdates, finishAttempt, flushReadyCommits]);
  flushPendingTextRef.current = flushPendingText;

  const sendText = useCallback(
    (target: StartTarget, text: string, method: 'keyboard' | 'button') => {
      const question = text.trim();
      // Bound the typed part of the existing 60 KiB finalization report.
      if (
        !question ||
        question.length > 8000 ||
        textTransitionRef.current ||
        !start(target)
      ) {
        return Promise.resolve(false);
      }
      const attempt = attemptRef.current!;
      const interrupted =
        outputTurnIndexRef.current !== null ||
        attempt.serverVoiceState === 'speaking';
      stopMicrophone();
      textTransitionRef.current = true;
      setViewState(previous => ({ ...previous, textPending: true }));
      if (attempt.analyticsEnabled)
        trackSafely(
          LIVE_VOICE_FOLLOW_UP_TEXT_SUBMIT_EVENT,
          buildLiveVoiceFollowUpTextAnalytics({
            ...attempt,
            submissionMethod: method,
            interrupted,
          }),
        );
      return new Promise<boolean>(resolve => {
        pendingTextRef.current = { text: question, resolve };
        flushPendingText();
      });
    },
    [flushPendingText, start, stopMicrophone, trackSafely],
  );

  const retry = useCallback(() => {
    if (admissionBlockedUntilRef.current > Date.now()) {
      return;
    }
    if (lastTargetRef.current) {
      start(lastTargetRef.current);
    }
  }, [start]);

  useEffect(() => {
    const deadline = viewState.retryAvailableAt;
    if (deadline === null) {
      return;
    }
    const timeout = window.setTimeout(
      () => {
        setViewState(previous =>
          previous.retryAvailableAt === deadline
            ? { ...previous, retryAvailableAt: null, retryable: true }
            : previous,
        );
      },
      Math.max(0, deadline - Date.now()),
    );
    return () => window.clearTimeout(timeout);
  }, [viewState.retryAvailableAt]);

  const toggleMuted = useCallback(() => {
    if (!mutedRef.current) stopMicrophone(true);
    else if (lastTargetRef.current) startMicrophone(lastTargetRef.current);
  }, [startMicrophone, stopMicrophone]);

  const end = useCallback(() => {
    finishAttempt({ reason: 'user_end', keepOpen: false });
  }, [finishAttempt]);

  const close = useCallback(() => {
    finishAttempt({
      reason:
        previousSessionScopeKeyRef.current !== sessionScopeKey
          ? 'lesson_changed'
          : 'user_close',
      keepOpen: false,
    });
  }, [finishAttempt, sessionScopeKey]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && attemptRef.current) {
        finishAttempt({ reason: 'page_hidden', keepOpen: false });
      }
      if (document.hidden) {
        closingFinalizersRef.current.forEach(finalize => finalize());
      }
    };
    const handlePageHide = () => {
      if (attemptRef.current) {
        finishAttempt({ reason: 'page_hidden', keepOpen: false });
      }
      closingFinalizersRef.current.forEach(finalize => finalize());
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('pagehide', handlePageHide);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('pagehide', handlePageHide);
    };
  }, [finishAttempt]);

  useEffect(() => {
    if (previousSessionScopeKeyRef.current === sessionScopeKey) {
      return;
    }
    previousSessionScopeKeyRef.current = sessionScopeKey;
    if (attemptRef.current) {
      finishAttempt({ reason: 'lesson_changed', keepOpen: false });
    }
    // Failed attempts no longer own a transport, but their retry target and
    // dialog still belong to the old scope. Keep credential admission intact.
    lastTargetRef.current = null;
    mutedRef.current = true;
    // The listen player consumes this reason to avoid resuming old lesson audio.
    setViewState({ ...initialState, endReason: 'lesson_changed' });
  }, [finishAttempt, sessionScopeKey]);

  useEffect(() => {
    unmountedRef.current = false;
    const closingFinalizers = closingFinalizersRef.current;
    return () => {
      unmountedRef.current = true;
      if (attemptRef.current) {
        finishAttemptRef.current?.({
          reason: 'lesson_changed',
          keepOpen: false,
        });
      }
      closingFinalizers.forEach(finalize => finalize());
    };
  }, []);

  return {
    ...viewState,
    start,
    startMicrophone,
    stopMicrophone,
    sendText,
    retry,
    toggleMuted,
    end,
    close,
  };
};
