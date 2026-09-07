'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { useTracking } from '@/hooks/useTracking';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import {
  encodeGeminiLiveAudioMessage,
  endLiveFollowUpSession,
  heartbeatLiveFollowUpSession,
  LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE,
  LiveFollowUpControlError,
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
  LIVE_VOICE_FOLLOW_UP_RENEWAL_ATTEMPT_EVENT,
  LIVE_VOICE_FOLLOW_UP_RENEWAL_RESULT_EVENT,
  LIVE_VOICE_FOLLOW_UP_SESSION_END_EVENT,
  LIVE_VOICE_FOLLOW_UP_PAUSE_EVENT,
  LIVE_VOICE_FOLLOW_UP_RESUME_EVENT,
  buildLiveVoiceFollowUpPauseAnalytics,
  shouldTrackLiveVoiceFollowUp,
  type LiveVoiceFollowUpEndReason,
  type LiveVoiceFollowUpErrorCode,
  type LiveVoiceFollowUpOutcome,
  type LiveVoiceFollowUpPauseReason,
  type LiveVoiceConnectionReason,
} from './liveVoiceFollowUpAnalytics';
import {
  LiveVoiceAudioUnavailableError,
  LiveVoiceFollowUpAudio,
} from './liveVoiceFollowUpAudio';
import { LiveFollowUpTurnWriter } from './liveFollowUpTurnWriter';
import { LiveFollowUpSessionAdmission } from './liveFollowUpSessionAdmission';
import { LiveFollowUpOwnership } from './liveFollowUpOwnership';
import {
  useLiveFollowUpReadiness,
  type LiveReadinessState,
} from './useLiveFollowUpReadiness';

const GEMINI_LIVE_SETUP_TIMEOUT_MS = 20_000;
// Redis rounds its matching absolute credential expiry up to a millisecond.
const CREDENTIAL_RESERVATION_MARGIN_MS = 1;
const CAPACITY_RETRY_BACKOFF_MS = 30_000;
const MAX_CONTROL_RETRY_DELAY_MS = 60_000;
const MAX_INPUT_AUDIO_FRAME_BYTES = 8 * 1024;
const MAX_BUFFERED_INPUT_AUDIO_BYTES = 8 * 1024;
const INPUT_ACTIVITY_THRESHOLD = 0.015 * 0x8000;
const INPUT_ACTIVITY_RELEASE_FRAMES = 6;
const MIN_HEARTBEAT_MS = 5_000;
const MAX_HEARTBEAT_MS = 30_000;
const HEARTBEAT_REQUEST_TIMEOUT_MS = 5_000;
const HEARTBEAT_RETRY_DELAY_MS = 1_000;
const RECOVERABLE_WEBSOCKET_CLOSE_CODES = new Set([
  1001, 1005, 1006, 1011, 1012, 1013,
]);

const isTransientHeartbeatFailure = (error: unknown) => {
  if (error instanceof LiveFollowUpControlError) return false;
  if (typeof error !== 'object' || error === null) return true;
  const status = 'status' in error ? error.status : undefined;
  if (typeof status === 'number') {
    return status === 408 || status === 429 || status >= 500;
  }
  // Business rejections (including expired bindings and auth failures) must
  // still stop the session. Raw network failures have no business code.
  return !('code' in error && typeof error.code === 'number');
};

const controlErrorCode = (
  error: LiveFollowUpControlError,
): LiveVoiceFollowUpErrorCode => {
  if (error.reason === 'capacity_exceeded') return 'capacity_exceeded';
  if (error.reason === 'pending' || error.reason === 'response_lost')
    return 'network_error';
  return error.reason === 'admission_unavailable'
    ? 'server_error'
    : 'session_create_failed';
};

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
  connectionReason: LiveVoiceConnectionReason;
  attemptReported: boolean;
  automaticRenewal: boolean;
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
  connectedPausePending: boolean;
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
  paused: boolean;
  state: LiveFollowUpState;
  muted: boolean;
  inputActive: boolean;
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
  readiness: LiveReadinessState;
  prepare: () => void;
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
  pause: (reason?: LiveVoiceFollowUpPauseReason) => void;
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
  preserveAudio?: boolean;
};

type RetainedAudio = {
  reason?: 'expiry' | 'connection_lost';
  audio: LiveVoiceFollowUpAudio;
  ready: Promise<void>;
  muted: boolean;
};

const initialState: LiveVoiceFollowUpViewState = {
  open: false,
  paused: false,
  state: 'ended',
  muted: true,
  inputActive: false,
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
  // Receipt bounds the latest expiry; request start bounds the earliest.
  // Never use the latest bound as proof that a credential can still resume.
  const sessionDeadlineRef = useRef<number | null>(null);
  const sessionValidUntilRef = useRef<number | null>(null);
  const credentialMayHaveExpired = useCallback(
    () =>
      sessionValidUntilRef.current !== null &&
      performance.now() >= sessionValidUntilRef.current,
    [],
  );
  const remainingSessionMs = useCallback(
    () =>
      sessionDeadlineRef.current === null
        ? Number.POSITIVE_INFINITY
        : sessionDeadlineRef.current - performance.now(),
    [],
  );
  const admissionRef = useRef<LiveFollowUpSessionAdmission | null>(null);
  if (!admissionRef.current)
    admissionRef.current = new LiveFollowUpSessionAdmission();
  const admissionBlockedUntilRef = useRef(0);
  const audioRef = useRef<LiveVoiceFollowUpAudio | null>(null);
  const audioActivationAbortRef = useRef<AbortController | null>(null);
  const audioReadyRef = useRef<Promise<LiveVoiceFollowUpAudio> | null>(null);
  const microphoneAbortRef = useRef<AbortController | null>(null);
  const microphoneSetupReadyRef = useRef<(() => void) | null>(null);
  const mutedRef = useRef(true);
  const inputActivityRef = useRef({ active: false, quietFrames: 0 });
  const expireSessionRef = useRef<(generation: number) => void>(() => {});
  const pausedRef = useRef(false);
  const resumeGenerationRef = useRef(0);
  const pauseRef = useRef<LiveVoiceFollowUpController['pause']>(() => {});
  const pauseFlushRef = useRef<{ generation: number } | null>(null);
  const lastFinalizationRef = useRef<Promise<boolean> | null>(null);
  const lastFinalizationFailedRef = useRef(false);
  const retryFinalizationRef = useRef<(() => Promise<boolean>) | null>(null);
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
  const timeoutTimerRef = useRef<number | null>(null);
  const setupTimerRef = useRef<number | null>(null);
  const heartbeatTimerRef = useRef<number | null>(null);
  const heartbeatRequestTimerRef = useRef<number | null>(null);
  const ownershipRef = useRef<LiveFollowUpOwnership | null>(null);
  const ownershipDeadlineRef = useRef(0);
  const takeoverPolicyRef = useRef(false);
  const connectionLossRenewalUsedRef = useRef(false);
  const renewLostConnectionRef = useRef<(generation: number) => boolean>(
    () => false,
  );
  const unmountedRef = useRef(false);
  const sessionScopeKey = `${shifuBid}:${outlineBid}:${sessionScope}:${previewMode ? 'preview' : 'learner'}`;
  const previousSessionScopeKeyRef = useRef(sessionScopeKey);
  const readiness = useLiveFollowUpReadiness(sessionScopeKey);
  const readinessRef = useRef(readiness);
  readinessRef.current = readiness;

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

  const applyControlRetry = useCallback((error: unknown) => {
    if (
      error instanceof LiveFollowUpControlError &&
      error.reason === 'admission_unavailable'
    ) {
      readinessRef.current.refresh();
    }
    if (
      error instanceof LiveFollowUpControlError &&
      typeof error.retryAfterMs === 'number' &&
      Number.isFinite(error.retryAfterMs) &&
      error.retryAfterMs > 0
    ) {
      admissionBlockedUntilRef.current = Math.max(
        admissionBlockedUntilRef.current,
        performance.now() +
          Math.min(MAX_CONTROL_RETRY_DELAY_MS, error.retryAfterMs),
      );
    }
  }, []);

  const reportAttemptStarted = useCallback(
    (attempt: ActiveAttempt) => {
      if (attempt.attemptReported) return;
      attempt.attemptReported = true;
      if (attempt.analyticsEnabled)
        trackSafely(
          attempt.automaticRenewal
            ? LIVE_VOICE_FOLLOW_UP_RENEWAL_ATTEMPT_EVENT
            : LIVE_VOICE_FOLLOW_UP_ATTEMPT_EVENT,
          buildLiveVoiceFollowUpAttemptAnalytics(
            attempt,
            attempt.connectionReason,
          ),
        );
    },
    [trackSafely],
  );

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
      reportAttemptStarted(attempt);
      if (!attempt.analyticsEnabled) {
        return;
      }
      trackSafely(
        attempt.automaticRenewal
          ? LIVE_VOICE_FOLLOW_UP_RENEWAL_RESULT_EVENT
          : LIVE_VOICE_FOLLOW_UP_RESULT_EVENT,
        buildLiveVoiceFollowUpResultAnalytics({
          shifuBid: attempt.shifuBid,
          outlineBid: attempt.outlineBid,
          learningMode: attempt.learningMode,
          surface: attempt.surface,
          outcome,
          errorCode,
          connectionReason: attempt.connectionReason,
        }),
      );
    },
    [trackSafely, reportAttemptStarted],
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
    ownershipRef.current?.stop();
    ownershipRef.current = null;
    ownershipDeadlineRef.current = 0;
    for (const timerRef of [
      timeoutTimerRef,
      setupTimerRef,
      heartbeatTimerRef,
      heartbeatRequestTimerRef,
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
        !accumulator ||
        pauseFlushRef.current?.generation === generation
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
    (reason: LiveVoiceFollowUpEndReason, preserveAudio = false) => {
      const endedAt = Date.now();
      const retainedMuted = mutedRef.current;
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
      inputActivityRef.current = { active: false, quietFrames: 0 };
      pausedRef.current = false;
      resumeGenerationRef.current += 1;
      pauseFlushRef.current = null;
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
      sessionDeadlineRef.current = null;
      sessionValidUntilRef.current = null;
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
      // Keep the already authorized microphone and running AudioContext only
      // for an active expiry handoff. Old callbacks stay attached through the
      // flush, so its played watermark cannot leak into the successor's turn 1.
      if (preserveAudio) audio?.setMuted(true);
      const stoppedAudio = preserveAudio
        ? audio?.interruptPlayback().catch(() => {})
        : audio?.stop().catch(() => {});
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
          return true;
        } catch {
          // Closing the binding is best-effort once every transcript is durable.
          // A failed /end must not poison all future input on this anchor.
          return writer ? !writer.hasPendingTurns : false;
        } finally {
          if (attempt) {
            reportSessionEnd(attempt, reason, endedAt);
          }
          closingFinalizersRef.current.delete(flushForUnload);
        }
      };
      // The next credential's server-built history must include this final
      // played turn. The writer already bounds finalization to 25 seconds.
      if (attempt && session) {
        const finalization = finalize();
        lastFinalizationRef.current = finalization;
        lastFinalizationFailedRef.current = false;
        void finalization.then(saved => {
          if (lastFinalizationRef.current === finalization)
            lastFinalizationFailedRef.current = !saved;
        });
        retryFinalizationRef.current = async () => {
          if (!writer) return false;
          if (!writer.hasPendingTurns) return true;
          try {
            await writer.retryFinish(endReason);
            return true;
          } catch {
            return !writer.hasPendingTurns;
          }
        };
      } else void finalize();
      return preserveAudio && audio
        ? { audio, ready: stoppedAudio!, muted: retainedMuted }
        : undefined;
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
      preserveAudio = false,
    }: FinishAttemptOptions) => {
      const attempt = attemptRef.current;
      const retainedAudio = teardownTransport(reason, preserveAudio);
      if (attempt) {
        if (!attempt.attemptResultReported) {
          reportAttemptResult(attempt, pendingOutcome, errorCode || 'none');
        }
      }
      attemptRef.current = null;
      if (!unmountedRef.current) {
        const retryAvailableAt =
          retryable && admissionBlockedUntilRef.current > performance.now()
            ? Date.now() + admissionBlockedUntilRef.current - performance.now()
            : null;
        setViewState(previous => ({
          ...previous,
          open: keepOpen,
          paused: false,
          state: 'ended',
          muted: true,
          inputActive: false,
          microphonePending: false,
          textPending: false,
          warning: false,
          errorCode,
          retryable: retryable && retryAvailableAt === null,
          retryAvailableAt,
          endReason: reason,
        }));
      }
      return retainedAudio;
    },
    [reportAttemptResult, teardownTransport],
  );
  finishAttemptRef.current = finishAttempt;

  const start = useCallback(
    (
      { anchorElementBid, surface }: StartTarget,
      retainedAudio?: RetainedAudio,
    ) => {
      const normalizedAnchor = anchorElementBid.trim();
      if (!normalizedAnchor || !shifuBid || !outlineBid) {
        return false;
      }
      if (sessionScope === 'classroom') return false;
      if (
        attemptRef.current &&
        sessionRef.current &&
        remainingSessionMs() <= 0
      ) {
        // A foreground click may beat the expiry timer after browser freezing.
        finishAttempt({ reason: 'timeout', keepOpen: true });
      }
      if (
        readinessRef.current.readiness !== 'ready' &&
        (!attemptRef.current ||
          attemptRef.current.anchorElementBid !== normalizedAnchor)
      )
        return false;
      if (
        attemptRef.current &&
        attemptRef.current.anchorElementBid !== normalizedAnchor
      ) {
        finishAttempt({ reason: 'replaced', keepOpen: true });
      }
      if (attemptRef.current) {
        const currentAttempt = attemptRef.current;
        if (pausedRef.current) {
          pausedRef.current = false;
          const resumeGeneration = ++resumeGenerationRef.current;
          requestExclusive(() => pauseRef.current('audio_replaced'));
          const audio = audioRef.current;
          setViewState(previous => ({
            ...previous,
            open: true,
            paused: false,
          }));
          if (audio) {
            currentAttempt.audioActivated = false;
            // Invoke native resume in this explicit input's activation stack.
            let resumeTimer: number | undefined;
            const ready = Promise.all([
              audio.resumeOutput(),
              sessionRef.current
                ? Promise.race([
                    heartbeatLiveFollowUpSession(
                      sessionRef.current.session_bid,
                    ),
                    new Promise<never>((_, reject) => {
                      resumeTimer = window.setTimeout(
                        () =>
                          reject(new Error('Live resume validation timed out')),
                        HEARTBEAT_REQUEST_TIMEOUT_MS,
                      );
                    }),
                  ]).finally(() => window.clearTimeout(resumeTimer))
                : Promise.resolve(),
            ]).then(() => {
              if (
                attemptRef.current !== currentAttempt ||
                pausedRef.current ||
                resumeGeneration !== resumeGenerationRef.current
              )
                return audio;
              accumulatorRef.current?.resumeOutput();
              currentAttempt.audioActivated = true;
              if (
                currentAttempt.analyticsEnabled &&
                currentAttempt.connectedPausePending
              )
                trackSafely(
                  LIVE_VOICE_FOLLOW_UP_RESUME_EVENT,
                  buildLiveVoiceFollowUpAttemptAnalytics(currentAttempt),
                );
              currentAttempt.connectedPausePending = false;
              flushPendingTextRef.current();
              return audio;
            });
            audioReadyRef.current = ready;
            void ready.catch(error => {
              if (
                attemptRef.current === currentAttempt &&
                !pausedRef.current &&
                resumeGeneration === resumeGenerationRef.current
              ) {
                applyControlRetry(error);
                finishAttempt({
                  reason: 'connection_error',
                  keepOpen: true,
                  errorCode:
                    error instanceof LiveFollowUpControlError
                      ? controlErrorCode(error)
                      : 'audio_unavailable',
                  retryable: true,
                });
              }
            });
          } else {
            accumulatorRef.current?.resumeOutput();
          }
        }
        return true;
      }
      if (admissionBlockedUntilRef.current > performance.now()) {
        lastTargetRef.current = { anchorElementBid: normalizedAnchor, surface };
        setViewState(previous => ({
          ...previous,
          open: true,
          anchorElementBid: normalizedAnchor,
          state: 'ended',
          retryable: false,
          retryAvailableAt:
            Date.now() + admissionBlockedUntilRef.current - performance.now(),
        }));
        return false;
      }
      const generation = ++generationRef.current;
      const target = { anchorElementBid: normalizedAnchor, surface };
      lastTargetRef.current = target;
      const attempt: ActiveAttempt = {
        connectionReason: retainedAudio
          ? (retainedAudio.reason ?? 'expiry')
          : 'user_start',
        attemptReported: false,
        automaticRenewal: !!retainedAudio,
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
        connectedPausePending: false,
        hadExchange: false,
      };
      attemptRef.current = attempt;
      if (!retainedAudio) connectionLossRenewalUsedRef.current = false;
      mutedRef.current = retainedAudio?.muted ?? true;
      pausedRef.current = false;
      setupReadyRef.current = false;
      const attemptAccumulator = new GeminiLiveTurnAccumulator();
      accumulatorRef.current = attemptAccumulator;
      let connectionDeadline: number | null = null;
      let sessionRequestStartedAt = performance.now();

      if (retainedAudio) reportAttemptStarted(attempt);
      setViewState({
        ...initialState,
        open: true,
        state: 'connecting',
        muted: mutedRef.current,
        microphonePending: !!retainedAudio && !mutedRef.current,
        anchorElementBid: normalizedAnchor,
      });
      requestExclusive(() => {
        pauseRef.current('audio_replaced');
      });

      const markConnectedIfReady = () => {
        const currentAttempt = attemptRef.current;
        if (
          currentAttempt?.generation !== generation ||
          !setupReadyRef.current ||
          !currentAttempt.audioActivated ||
          currentAttempt.serverVoiceState === null ||
          (sessionRef.current?.ownership_timeout_ms &&
            performance.now() >= ownershipDeadlineRef.current)
        ) {
          return;
        }
        if (
          connectionDeadline !== null &&
          performance.now() >= connectionDeadline
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
        if (setupTimerRef.current !== null) {
          window.clearTimeout(setupTimerRef.current);
          setupTimerRef.current = null;
        }
        audioRef.current?.setMuted(mutedRef.current || pausedRef.current);
        if (!mutedRef.current) {
          setViewState(previous => ({ ...previous, microphonePending: false }));
        }
        microphoneSetupReadyRef.current?.();
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

      const startSessionTimers = (currentAttempt: ActiveAttempt) => {
        if (currentAttempt.serverReadyAt !== null) {
          return true;
        }
        const now = Date.now();
        const remainingMs = remainingSessionMs();
        if (!Number.isFinite(remainingMs) || remainingMs <= 0) {
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
        timeoutTimerRef.current = window.setTimeout(() => {
          expireSessionRef.current(generation);
        }, remainingMs + CREDENTIAL_RESERVATION_MARGIN_MS);
        return true;
      };

      const audioActivationAbort = new AbortController();
      audioActivationAbortRef.current = audioActivationAbort;
      const audioCallbacks = {
        onInputFrame: (frame: ArrayBuffer) => {
          const currentAttempt = attemptRef.current;
          const websocket = websocketRef.current;
          if (
            currentAttempt?.generation !== generation ||
            mutedRef.current ||
            pausedRef.current ||
            !setupReadyRef.current ||
            (sessionRef.current?.ownership_timeout_ms &&
              performance.now() >= ownershipDeadlineRef.current) ||
            websocket?.readyState !== WebSocket.OPEN ||
            frame.byteLength > MAX_INPUT_AUDIO_FRAME_BYTES
          ) {
            return;
          }
          if (frame.byteLength > 0 && frame.byteLength % 2 === 0) {
            const samples = new Int16Array(frame);
            let energy = 0;
            for (const sample of samples) energy += sample * sample;
            const audible =
              Math.sqrt(energy / samples.length) >= INPUT_ACTIVITY_THRESHOLD;
            const activity = inputActivityRef.current;
            activity.quietFrames = audible ? 0 : activity.quietFrames + 1;
            const active =
              audible ||
              (activity.active &&
                activity.quietFrames < INPUT_ACTIVITY_RELEASE_FRAMES);
            if (active !== activity.active) {
              activity.active = active;
              setViewState(previous => ({ ...previous, inputActive: active }));
            }
          }
          if (
            websocket.bufferedAmount + frame.byteLength * 2 >
            MAX_BUFFERED_INPUT_AUDIO_BYTES
          )
            return;
          sendWebSocketPayload(websocket, encodeGeminiLiveAudioMessage(frame));
        },
        onPlaybackProgress: (turnIndex: number, playedBytes: number) => {
          attemptAccumulator.recordPlaybackProgress(turnIndex, playedBytes);
          flushReadyCommits(generation);
        },
        onPlaybackComplete: (turnIndex: number) => {
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
      };

      let audioPromise: Promise<LiveVoiceFollowUpAudio>;
      try {
        if (retainedAudio) {
          // Make cancellation/pause immediately reach the retained graph even
          // while its old playback watermark is still being acknowledged.
          audioRef.current = retainedAudio.audio;
          audioPromise = retainedAudio.ready.then(() => {
            if (attemptRef.current?.generation === generation)
              retainedAudio.audio.setCallbacks(audioCallbacks);
            return retainedAudio.audio;
          });
        } else {
          audioPromise = LiveVoiceFollowUpAudio.activate(
            audioCallbacks,
            audioActivationAbort.signal,
          );
        }
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
          if (sessionRef.current?.ownership_timeout_ms)
            audio.setAuthorizationDeadline(ownershipDeadlineRef.current);
          audio.setMuted(mutedRef.current || !setupReadyRef.current);
          if (pausedRef.current) void audio.pauseOutput();
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

      const armConnectionTimeout = (resuming = false) => {
        if (connectionDeadline === null || resuming)
          connectionDeadline = performance.now() + GEMINI_LIVE_SETUP_TIMEOUT_MS;
        if (setupTimerRef.current !== null) {
          window.clearTimeout(setupTimerRef.current);
        }
        setupTimerRef.current = window.setTimeout(
          () => {
            setupTimerRef.current = null;
            const currentAttempt = attemptRef.current;
            if (
              currentAttempt?.generation !== generation ||
              (setupReadyRef.current && currentAttempt.audioActivated)
            ) {
              return;
            }
            if (resuming && renewLostConnectionRef.current(generation)) return;
            finishAttempt({
              reason: 'connection_error',
              keepOpen: true,
              errorCode: 'network_error',
              retryable: true,
              pendingOutcome: 'failed',
            });
          },
          Math.max(0, connectionDeadline - performance.now()),
        );
      };

      let sessionPromise: Promise<LiveFollowUpSession>;
      try {
        const retryPreviousFinalization = lastFinalizationFailedRef.current;
        const createSession = () => {
          if (attemptRef.current?.generation !== generation)
            throw new Error('Live session startup cancelled');
          armConnectionTimeout();
          sessionRequestStartedAt = performance.now();
          return admissionRef.current!.create(
            shifuBid,
            outlineBid,
            {
              anchor_element_bid: normalizedAnchor,
              preview_mode: previewMode,
              learning_mode: learningMode,
              surface,
            },
            () =>
              attemptRef.current?.generation === generation &&
              (connectionDeadline === null ||
                performance.now() < connectionDeadline),
            reason => {
              if (
                attemptRef.current?.generation !== generation ||
                attempt.attemptReported
              )
                return;
              attempt.connectionReason = reason;
              reportAttemptStarted(attempt);
            },
            !retainedAudio,
          );
        };
        // New takeovers snapshot durable server history; a dead old page cannot
        // be required to complete its last HTTP report before the learner speaks.
        sessionPromise =
          !takeoverPolicyRef.current && lastFinalizationRef.current
            ? lastFinalizationRef.current.then(async saved => {
                if (!saved) {
                  if (attemptRef.current?.generation !== generation)
                    throw new Error('Live session startup cancelled');
                  // One click may wait for the existing closing budget OR
                  // retry an already failed one, never chain both budgets.
                  if (!retryPreviousFinalization)
                    throw new Error('Previous Live history was not saved');
                  const recovery = retryFinalizationRef.current?.();
                  if (recovery) {
                    lastFinalizationRef.current = recovery;
                    lastFinalizationFailedRef.current = false;
                    void recovery.then(recovered => {
                      if (lastFinalizationRef.current === recovery)
                        lastFinalizationFailedRef.current = !recovered;
                    });
                  }
                  if (!(await recovery))
                    throw new Error('Previous Live history was not saved');
                }
                return createSession();
              })
            : createSession();
      } catch (error) {
        sessionPromise = Promise.reject(error);
      }

      let unexpectedResumptionUsed = false;
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
        audioRef.current?.setMuted(true);
        inputActivityRef.current = { active: false, quietFrames: 0 };
        setViewState(previous => ({
          ...previous,
          inputActive: false,
          microphonePending: previous.microphonePending || !mutedRef.current,
        }));
        armConnectionTimeout(resumptionHandle !== null);
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
          if (
            attemptRef.current?.generation !== generation ||
            websocketRef.current !== websocket
          ) {
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
            websocketRef.current !== websocket ||
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
            if (credentialMayHaveExpired()) {
              expireSessionRef.current(generation);
              return;
            }
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
              if (!startSessionTimers(currentAttempt)) {
                return;
              }
              markConnectedIfReady();
              if (attemptRef.current?.generation !== generation) return;
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
            !pausedRef.current &&
            (!session.ownership_timeout_ms ||
              performance.now() < ownershipDeadlineRef.current) &&
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
            if (credentialMayHaveExpired()) {
              expireSessionRef.current(generation);
              return;
            }
            const handle = resumptionHandleRef.current;
            if (!handle) {
              if (renewLostConnectionRef.current(generation)) return;
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
          if (
            attemptRef.current?.generation !== generation ||
            websocketRef.current !== websocket
          ) {
            return;
          }
          if (credentialMayHaveExpired()) {
            expireSessionRef.current(generation);
            return;
          }
          // The close event carries the protocol status. Wait for it before
          // deciding whether an established session can resume safely.
          if (setupReadyRef.current && resumptionHandleRef.current) return;
          if (renewLostConnectionRef.current(generation)) return;
          finishAttempt({
            reason: 'connection_error',
            keepOpen: true,
            errorCode: 'websocket_failed',
            retryable: true,
            pendingOutcome: 'failed',
          });
        };
        websocket.onclose = event => {
          if (
            attemptRef.current?.generation !== generation ||
            websocketRef.current !== websocket
          ) {
            return;
          }
          if (credentialMayHaveExpired()) {
            expireSessionRef.current(generation);
            return;
          }
          const handle = resumptionHandleRef.current;
          if (
            setupReadyRef.current &&
            handle &&
            !unexpectedResumptionUsed &&
            !textTransitionRef.current &&
            RECOVERABLE_WEBSOCKET_CLOSE_CODES.has(event.code) &&
            !credentialMayHaveExpired()
          ) {
            unexpectedResumptionUsed = true;
            reconnectingRef.current = true;
            attemptRef.current.serverVoiceState = null;
            setViewState(previous => ({ ...previous, state: 'reconnecting' }));
            openGeminiSocket(session, handle);
            return;
          }
          if (
            RECOVERABLE_WEBSOCKET_CLOSE_CODES.has(event.code) &&
            renewLostConnectionRef.current(generation)
          )
            return;
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
        .then(async session => {
          if (attemptRef.current?.generation === generation)
            takeoverPolicyRef.current =
              session.rotation_enabled === true &&
              !!session.ownership_timeout_ms;
          // Only the old-server compatibility path consults wall time, once.
          // All subsequent checks, timers, and cooldowns use monotonic time.
          const lifetime =
            session.expires_in_ms === undefined
              ? Date.parse(session.expires_at) - Date.now()
              : typeof session.expires_in_ms === 'number' &&
                  Number.isFinite(session.expires_in_ms) &&
                  session.expires_in_ms >= 0 &&
                  session.expires_in_ms <= 900_000
                ? session.expires_in_ms
                : Number.NaN;
          const expiresAt = performance.now() + lifetime;
          if (
            session.rotation_enabled !== true &&
            generationRef.current === generation &&
            Number.isFinite(expiresAt)
          ) {
            admissionBlockedUntilRef.current = Math.max(
              admissionBlockedUntilRef.current,
              expiresAt + CREDENTIAL_RESERVATION_MARGIN_MS,
            );
          }
          if (attemptRef.current?.generation !== generation) {
            if (
              !unmountedRef.current &&
              generationRef.current === generation &&
              session.rotation_enabled !== true
            ) {
              setViewState(previous =>
                previous.open && previous.state === 'ended'
                  ? {
                      ...previous,
                      retryable: false,
                      retryAvailableAt:
                        Date.now() +
                        admissionBlockedUntilRef.current -
                        performance.now(),
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
          sessionDeadlineRef.current = expiresAt;
          // The server sampled its remaining lifetime somewhere within this
          // request. Subtract the full elapsed request for a conservative
          // resumption bound, but retain the receipt bound for safe admission.
          sessionValidUntilRef.current =
            session.expires_in_ms === undefined
              ? expiresAt
              : sessionRequestStartedAt + lifetime;
          if (
            connectionDeadline !== null &&
            performance.now() >= connectionDeadline
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
          if (session.ownership_timeout_ms && session.admission_revision) {
            audioRef.current?.setAuthorizationDeadline(0);
            const ownership = new LiveFollowUpOwnership(
              session.session_bid,
              session.admission_revision,
              deadline => {
                if (attemptRef.current?.generation !== generation) return;
                ownershipDeadlineRef.current = deadline;
                audioRef.current?.setAuthorizationDeadline(deadline);
                markConnectedIfReady();
              },
              error => {
                if (attemptRef.current?.generation !== generation) return;
                const replaced =
                  error instanceof LiveFollowUpControlError &&
                  error.reason === 'ownership_conflict';
                if (!replaced && credentialMayHaveExpired()) {
                  expireSessionRef.current(generation);
                  return;
                }
                finishAttempt({
                  reason: replaced ? 'replaced' : 'connection_error',
                  keepOpen: true,
                  errorCode: replaced ? null : 'server_error',
                  retryable: true,
                  pendingOutcome: replaced ? 'cancelled' : 'failed',
                });
              },
            );
            ownershipRef.current = ownership;
            await ownership.start(session.previous_admission_revision);
            if (attemptRef.current?.generation !== generation) {
              ownership.stop();
              return;
            }
            openGeminiSocket(session, null);
            return;
          }
          openGeminiSocket(session, null);
          const heartbeatMs = Math.min(
            MAX_HEARTBEAT_MS,
            Math.max(MIN_HEARTBEAT_MS, session.heartbeat_interval_ms),
          );
          const heartbeat = async (isRetry = false) => {
            if (attemptRef.current?.generation !== generation) return;
            heartbeatTimerRef.current = null;
            const requestedAt = performance.now();
            let requestTimer: number | null = null;
            try {
              await Promise.race([
                heartbeatLiveFollowUpSession(session.session_bid),
                new Promise<never>((_, reject) => {
                  requestTimer = window.setTimeout(
                    () => reject(new Error('Live heartbeat timed out')),
                    HEARTBEAT_REQUEST_TIMEOUT_MS,
                  );
                  heartbeatRequestTimerRef.current = requestTimer;
                }),
              ]);
              if (attemptRef.current?.generation === generation) {
                heartbeatTimerRef.current = window.setTimeout(
                  () => void heartbeat(),
                  Math.max(0, heartbeatMs - (performance.now() - requestedAt)),
                );
              }
            } catch (error) {
              if (attemptRef.current?.generation !== generation) return;
              if (credentialMayHaveExpired()) {
                expireSessionRef.current(generation);
                return;
              }
              // Background timers/network can be throttled. The fixed-lifetime
              // binding remains valid; explicit foreground input rechecks it.
              if (pausedRef.current && isTransientHeartbeatFailure(error)) {
                heartbeatTimerRef.current = window.setTimeout(
                  () => void heartbeat(),
                  heartbeatMs,
                );
                return;
              }
              if (!isRetry && isTransientHeartbeatFailure(error)) {
                // Bound foreground health recovery; this does not extend the
                // credential's fixed lifetime or its capacity reservation.
                heartbeatTimerRef.current = window.setTimeout(
                  () => void heartbeat(true),
                  HEARTBEAT_RETRY_DELAY_MS,
                );
              } else {
                applyControlRetry(error);
                finishAttempt({
                  reason: 'connection_error',
                  keepOpen: true,
                  errorCode:
                    error instanceof LiveFollowUpControlError
                      ? controlErrorCode(error)
                      : 'server_error',
                  retryable: true,
                  pendingOutcome: 'failed',
                });
              }
            } finally {
              if (requestTimer !== null) window.clearTimeout(requestTimer);
              if (heartbeatRequestTimerRef.current === requestTimer) {
                heartbeatRequestTimerRef.current = null;
              }
            }
          };
          heartbeatTimerRef.current = window.setTimeout(
            () => void heartbeat(),
            heartbeatMs,
          );
        })
        .catch(error => {
          if (attemptRef.current?.generation === generation) {
            applyControlRetry(error);
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
                performance.now() + CAPACITY_RETRY_BACKOFF_MS,
              );
            }
            finishAttempt({
              reason: 'connection_error',
              keepOpen: true,
              errorCode:
                connectionDeadline !== null &&
                performance.now() >= connectionDeadline
                  ? 'network_error'
                  : error instanceof LiveFollowUpControlError
                    ? controlErrorCode(error)
                    : capacityExceeded
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
      applyControlRetry,
      applyTranscriptUpdates,
      credentialMayHaveExpired,
      finishAttempt,
      flushReadyCommits,
      learningMode,
      outlineBid,
      previewMode,
      reportAttemptResult,
      reportAttemptStarted,
      remainingSessionMs,
      requestExclusive,
      scheduleCommitFlush,
      shifuBid,
      sessionScope,
      trackSafely,
    ],
  );

  expireSessionRef.current = generation => {
    const attempt = attemptRef.current;
    if (!attempt || attempt.generation !== generation) return;
    const remaining = remainingSessionMs() + CREDENTIAL_RESERVATION_MARGIN_MS;
    if (
      sessionRef.current?.rotation_enabled !== true &&
      Number.isFinite(remaining) &&
      remaining > 0
    ) {
      // Transport ended in the response-latency uncertainty window. Do not
      // resume a possibly expired token or mint before its risk lease drains.
      setupReadyRef.current = false;
      reconnectingRef.current = true;
      inputActivityRef.current = { active: false, quietFrames: 0 };
      audioRef.current?.setMuted(true);
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
        )
          websocket.close(1000, 'session expiring');
      }
      setViewState(previous => ({
        ...previous,
        state: 'reconnecting',
        inputActive: false,
        microphonePending: !mutedRef.current,
      }));
      if (timeoutTimerRef.current !== null)
        window.clearTimeout(timeoutTimerRef.current);
      timeoutTimerRef.current = window.setTimeout(
        () => expireSessionRef.current(generation),
        remaining,
      );
      return;
    }
    const connected = attempt.connectedAt !== null;
    const renew =
      connected &&
      !pausedRef.current &&
      !mutedRef.current &&
      !document.hidden &&
      !!audioRef.current &&
      readinessRef.current.readiness === 'ready';
    const audio = finishAttempt({
      reason: 'timeout',
      keepOpen: true,
      preserveAudio: renew,
      retryable: !connected,
      errorCode: connected ? null : 'server_error',
      pendingOutcome: connected ? 'cancelled' : 'failed',
    });
    if (audio && !start(attempt, audio))
      void audio.audio.stop().catch(() => {});
  };

  renewLostConnectionRef.current = generation => {
    const attempt = attemptRef.current;
    if (
      !attempt ||
      attempt.generation !== generation ||
      attempt.connectedAt === null ||
      connectionLossRenewalUsedRef.current ||
      sessionRef.current?.rotation_enabled !== true ||
      mutedRef.current ||
      pausedRef.current ||
      document.hidden ||
      !audioRef.current ||
      readinessRef.current.readiness !== 'ready'
    )
      return false;
    connectionLossRenewalUsedRef.current = true;
    const audio = finishAttempt({
      reason: 'connection_closed',
      keepOpen: true,
      preserveAudio: true,
    });
    if (audio && !start(attempt, { ...audio, reason: 'connection_lost' }))
      void audio.audio.stop().catch(() => {});
    return true;
  };

  const stopMicrophone = useCallback(
    (explicit = false) => {
      const wasEnabled = !mutedRef.current;
      const attempt = attemptRef.current;
      microphoneAbortRef.current?.abort();
      microphoneAbortRef.current = null;
      mutedRef.current = true;
      inputActivityRef.current = { active: false, quietFrames: 0 };
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
        inputActive: false,
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
      if (explicit && attempt) pauseRef.current('microphone_off');
    },
    [trackSafely],
  );

  const startMicrophone = useCallback(
    (target: StartTarget) => {
      const ownsTarget =
        !attemptRef.current ||
        attemptRef.current.anchorElementBid === target.anchorElementBid.trim();
      if (
        (ownsTarget &&
          (microphoneAbortRef.current ||
            !mutedRef.current ||
            textTransitionRef.current)) ||
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
            audio.setMuted(!setupReadyRef.current);
            setViewState(previous => ({
              ...previous,
              muted: false,
              microphonePending: !setupReadyRef.current,
            }));
            if (!setupReadyRef.current) {
              await new Promise<void>((resolve, reject) => {
                const cleanup = () => {
                  if (microphoneSetupReadyRef.current === complete)
                    microphoneSetupReadyRef.current = null;
                  abort.signal.removeEventListener('abort', cancel);
                };
                const complete = () => {
                  cleanup();
                  resolve();
                };
                const cancel = () => {
                  cleanup();
                  reject(
                    new DOMException('Microphone cancelled', 'AbortError'),
                  );
                };
                microphoneSetupReadyRef.current = complete;
                abort.signal.addEventListener('abort', cancel, { once: true });
                if (abort.signal.aborted) cancel();
              });
            }
            if (abort.signal.aborted || attemptRef.current !== attempt)
              throw new DOMException('Microphone cancelled', 'AbortError');
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

  const pause = useCallback(
    (reason: LiveVoiceFollowUpPauseReason = 'panel_closed') => {
      const attempt = attemptRef.current;
      if (!attempt) return;
      if (pausedRef.current) {
        if (reason !== 'microphone_off')
          setViewState(previous => ({ ...previous, open: false }));
        return;
      }
      pausedRef.current = true;
      // Setup may finish while paused. Only an already-connected pause owns a
      // matching resume event; connection readiness alone cannot establish it.
      attempt.connectedPausePending = attempt.connectedAt !== null;
      // Paused output is no longer speaking even if Gemini finishes later.
      // Neither the resume hint nor a future submit should inherit that state.
      if (attempt.serverVoiceState === 'speaking')
        attempt.serverVoiceState = 'listening';
      resumeGenerationRef.current += 1;
      if (!mutedRef.current || microphoneAbortRef.current) stopMicrophone();
      pendingTextRef.current?.resolve(false);
      pendingTextRef.current = null;
      accumulatorRef.current?.pauseOutput();
      textTransitionRef.current =
        accumulatorRef.current?.textHandoffPending ?? false;
      // A submitted interruption still needs the successor's acknowledgement.
      // Preserve its identity so terminal events received while paused can
      // release the handoff gate; unsent input has already returned to draft.
      if (!textTransitionRef.current) {
        expectedTextResponseTurnRef.current = null;
        if (textTimerRef.current !== null)
          window.clearTimeout(textTimerRef.current);
        textTimerRef.current = null;
      }
      outputTurnIndexRef.current = null;
      const audio = audioRef.current;
      if (audio) {
        const pendingFlush = { generation: attempt.generation };
        pauseFlushRef.current = pendingFlush;
        void audio
          .pauseOutput()
          .catch(() => {})
          .finally(() => {
            if (pauseFlushRef.current !== pendingFlush) return;
            pauseFlushRef.current = null;
            flushReadyCommits(attempt.generation);
          });
      }
      // Course playback may resume as soon as its panel closes. Late Live PCM
      // remains suppressed independently of this global ownership release.
      releaseExclusive();
      setViewState(previous => ({
        ...previous,
        open: reason === 'microphone_off' ? previous.open : false,
        paused: true,
        state: previous.state === 'speaking' ? 'listening' : previous.state,
        muted: true,
        microphonePending: false,
        textPending: textTransitionRef.current,
      }));
      if (attempt.connectedAt !== null && attempt.analyticsEnabled)
        trackSafely(
          LIVE_VOICE_FOLLOW_UP_PAUSE_EVENT,
          buildLiveVoiceFollowUpPauseAnalytics({ ...attempt, reason }),
        );
    },
    [flushReadyCommits, releaseExclusive, stopMicrophone, trackSafely],
  );
  pauseRef.current = pause;

  const flushPendingText = useCallback(() => {
    const pending = pendingTextRef.current;
    const attempt = attemptRef.current;
    const accumulator = accumulatorRef.current;
    if (
      !pending ||
      pausedRef.current ||
      !attempt ||
      !accumulator ||
      !setupReadyRef.current ||
      (sessionRef.current?.ownership_timeout_ms &&
        performance.now() >= ownershipDeadlineRef.current) ||
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
        (textTransitionRef.current &&
          attemptRef.current?.anchorElementBid ===
            target.anchorElementBid.trim()) ||
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
    if (admissionBlockedUntilRef.current > performance.now()) {
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
      Math.max(0, admissionBlockedUntilRef.current - performance.now()),
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
        pause('page_hidden');
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
  }, [finishAttempt, pause]);

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
    readiness: readiness.readiness,
    prepare: readiness.prepare,
    start,
    startMicrophone,
    stopMicrophone,
    sendText,
    retry,
    toggleMuted,
    end,
    close,
    pause,
  };
};
