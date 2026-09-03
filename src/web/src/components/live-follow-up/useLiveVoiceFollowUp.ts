'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { useTracking } from '@/c-common/hooks/useTracking';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import {
  commitLiveFollowUpTurn,
  createLiveFollowUpSession,
  encodeGeminiLiveAudioMessage,
  endLiveFollowUpSession,
  heartbeatLiveFollowUpSession,
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

const SESSION_WARNING_MS = 14 * 60 * 1000 + 30 * 1000;
const SESSION_TIMEOUT_MS = 15 * 60 * 1000;
const GEMINI_LIVE_SETUP_TIMEOUT_MS = 20_000;
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

type StartTarget = {
  anchorElementBid: string;
  surface: LiveFollowUpSurface;
};

type ActiveAttempt = StartTarget & {
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

export type LiveVoiceFollowUpViewState = {
  open: boolean;
  state: LiveFollowUpState;
  muted: boolean;
  warning: boolean;
  transcripts: LiveVoiceTranscript[];
  errorCode: LiveVoiceFollowUpErrorCode | null;
  retryable: boolean;
  endReason: LiveVoiceFollowUpEndReason | null;
};

export type LiveVoiceFollowUpController = LiveVoiceFollowUpViewState & {
  start: (target: StartTarget) => void;
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
  onTurnCommitted?: (turn: {
    anchorElementBid: string;
    turnIndex: number;
    userTranscript: string;
    assistantTranscript: string;
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
  muted: false,
  warning: false,
  transcripts: [],
  errorCode: null,
  retryable: false,
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

const sortTranscripts = (items: LiveVoiceTranscript[]) =>
  [...items].sort((left, right) => {
    if (left.turnIndex !== right.turnIndex) {
      return left.turnIndex - right.turnIndex;
    }
    if (left.role === right.role) {
      return 0;
    }
    return left.role === 'user' ? -1 : 1;
  });

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
  const audioRef = useRef<LiveVoiceFollowUpAudio | null>(null);
  const mutedRef = useRef(false);
  const setupReadyRef = useRef(false);
  const reconnectingRef = useRef(false);
  const resumptionHandleRef = useRef<string | null>(null);
  const outputTurnIndexRef = useRef<number | null>(null);
  const transcriptsRef = useRef<LiveVoiceTranscript[]>([]);
  const accumulatorRef = useRef<GeminiLiveTurnAccumulator | null>(null);
  const commitTimerRef = useRef<number | null>(null);
  const commitChainRef = useRef<Promise<void> | null>(null);
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
    learningMode,
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
      if (!analyticsEnabled) {
        return;
      }
      trackSafely(
        LIVE_VOICE_FOLLOW_UP_RESULT_EVENT,
        buildLiveVoiceFollowUpResultAnalytics({
          shifuBid,
          outlineBid,
          learningMode,
          surface: attempt.surface,
          outcome,
          errorCode,
        }),
      );
    },
    [analyticsEnabled, learningMode, outlineBid, shifuBid, trackSafely],
  );

  const reportSessionEnd = useCallback(
    (attempt: ActiveAttempt, reason: LiveVoiceFollowUpEndReason) => {
      if (
        attempt.sessionEndReported ||
        attempt.connectedAt === null ||
        !analyticsEnabled
      ) {
        return;
      }
      attempt.sessionEndReported = true;
      trackSafely(
        LIVE_VOICE_FOLLOW_UP_SESSION_END_EVENT,
        buildLiveVoiceFollowUpSessionEndAnalytics({
          shifuBid,
          outlineBid,
          learningMode,
          surface: attempt.surface,
          durationMs: Date.now() - attempt.connectedAt,
          hadExchange: attempt.hadExchange,
          endReason: reason,
        }),
      );
    },
    [analyticsEnabled, learningMode, outlineBid, shifuBid, trackSafely],
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
        transcriptsRef.current = sortTranscripts([
          ...transcriptsRef.current.filter(
            transcript =>
              transcript.turnIndex !== update.turnIndex ||
              transcript.role !== update.role,
          ),
          update,
        ]);
      }
      setViewState(previous => ({
        ...previous,
        transcripts: transcriptsRef.current,
      }));
    },
    [],
  );

  const persistCommits = useCallback(
    (
      sessionBid: string,
      anchorElementBid: string,
      commits: GeminiLiveTurnCommit[],
      generation: number,
    ) => {
      for (const commit of commits) {
        const persistCommit = async () => {
          await commitLiveFollowUpTurn(sessionBid, {
            turn_index: commit.turnIndex,
            user_transcript: commit.userTranscript,
            played_answer_transcript: commit.playedAnswerTranscript,
            interrupted: commit.interrupted,
            usage_metadata: commit.usageMetadata,
            latency_ms: commit.latencyMs,
          });
          const activeAttempt = attemptRef.current;
          if (activeAttempt?.generation === generation) {
            activeAttempt.hadExchange = true;
          }
          try {
            onTurnCommitted?.({
              anchorElementBid,
              turnIndex: commit.turnIndex,
              userTranscript: commit.userTranscript,
              assistantTranscript: commit.playedAnswerTranscript,
            });
          } catch {}
        };
        const previousCommit = commitChainRef.current;
        const pendingCommit = previousCommit
          ? previousCommit.then(persistCommit)
          : persistCommit();
        const handledCommit = pendingCommit.catch(() => {
          if (attemptRef.current?.generation === generation) {
            finishAttemptRef.current?.({
              reason: 'connection_error',
              keepOpen: true,
              errorCode: 'server_error',
              retryable: true,
              pendingOutcome: 'failed',
            });
          }
        });
        commitChainRef.current = handledCommit;
        void handledCommit.then(() => {
          if (commitChainRef.current === handledCommit) {
            commitChainRef.current = null;
          }
        });
      }
    },
    [onTurnCommitted],
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
      persistCommits(
        session.session_bid,
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
      commitTimerRef.current = window.setTimeout(() => {
        commitTimerRef.current = null;
        flushReadyCommits(generation);
      }, GEMINI_LIVE_RECONCILIATION_MS);
    },
    [flushReadyCommits],
  );

  const teardownTransport = useCallback(
    (reason: LiveVoiceFollowUpEndReason) => {
      clearTimers();
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
      }

      const attempt = attemptRef.current;
      const session = sessionRef.current;
      const accumulator = accumulatorRef.current;
      sessionRef.current = null;
      accumulatorRef.current = null;
      const audio = audioRef.current;
      audioRef.current = null;

      if (attempt && session && accumulator) {
        persistCommits(
          session.session_bid,
          attempt.anchorElementBid,
          accumulator.finishSession(),
          attempt.generation,
        );
      }
      const pendingCommit = commitChainRef.current;
      const finalize = async () => {
        await audio?.stop().catch(() => {});
        if (attempt && session) {
          await pendingCommit?.catch(() => {});
          await endLiveFollowUpSession(
            session.session_bid,
            directSessionEndReason(reason),
          ).catch(() => {});
        }
        if (
          websocket?.readyState === WebSocket.OPEN ||
          websocket?.readyState === WebSocket.CONNECTING
        ) {
          websocket.close(1000, 'session ended');
        }
      };
      void finalize();
      releaseExclusive();
    },
    [clearTimers, persistCommits, releaseExclusive],
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
        reportSessionEnd(attempt, reason);
      }
      attemptRef.current = null;
      if (!unmountedRef.current) {
        setViewState(previous => ({
          ...previous,
          open: keepOpen,
          state: 'ended',
          warning: false,
          errorCode,
          retryable,
          endReason: reason,
        }));
      }
    },
    [reportAttemptResult, reportSessionEnd, teardownTransport],
  );
  finishAttemptRef.current = finishAttempt;

  const start = useCallback(
    ({ anchorElementBid, surface }: StartTarget) => {
      const normalizedAnchor = anchorElementBid.trim();
      if (!normalizedAnchor || !shifuBid || !outlineBid) {
        return;
      }
      if (attemptRef.current) {
        finishAttempt({ reason: 'replaced', keepOpen: false });
      }

      const generation = ++generationRef.current;
      const target = { anchorElementBid: normalizedAnchor, surface };
      lastTargetRef.current = target;
      const attempt: ActiveAttempt = {
        ...target,
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
      mutedRef.current = false;
      setupReadyRef.current = false;
      transcriptsRef.current = [];
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
      setViewState({ ...initialState, open: true, state: 'connecting' });
      requestExclusive(() => {
        finishAttempt({ reason: 'replaced', keepOpen: false });
      });

      const markConnectedIfReady = () => {
        const currentAttempt = attemptRef.current;
        if (
          currentAttempt?.generation !== generation ||
          currentAttempt.connectedAt !== null ||
          !currentAttempt.audioActivated ||
          currentAttempt.serverVoiceState === null
        ) {
          return;
        }
        currentAttempt.connectedAt = Date.now();
        reportAttemptResult(currentAttempt, 'success', 'none');
        setViewState(previous => ({
          ...previous,
          state: currentAttempt.serverVoiceState || 'listening',
        }));
      };

      const startSessionTimers = (currentAttempt: ActiveAttempt) => {
        if (currentAttempt.serverReadyAt !== null) {
          return;
        }
        currentAttempt.serverReadyAt = Date.now();
        warningTimerRef.current = window.setTimeout(() => {
          setViewState(previous => ({ ...previous, warning: true }));
        }, SESSION_WARNING_MS);
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
        }, SESSION_TIMEOUT_MS);
      };

      const activateAudio = () =>
        LiveVoiceFollowUpAudio.activate({
          onInputFrame: frame => {
            const currentAttempt = attemptRef.current;
            const websocket = websocketRef.current;
            if (
              currentAttempt?.generation !== generation ||
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
                setViewState(previous => ({ ...previous, state: 'listening' }));
              }
            }
          },
        });

      let audioPromise: Promise<LiveVoiceFollowUpAudio>;
      try {
        audioPromise = activateAudio();
      } catch (error) {
        audioPromise = Promise.reject(error);
      }
      void audioPromise
        .then(audio => {
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
        if (setupTimerRef.current !== null) {
          window.clearTimeout(setupTimerRef.current);
        }
        setupTimerRef.current = window.setTimeout(() => {
          setupTimerRef.current = null;
          if (
            attemptRef.current?.generation !== generation ||
            setupReadyRef.current
          ) {
            return;
          }
          finishAttempt({
            reason: 'connection_error',
            keepOpen: true,
            errorCode: 'network_error',
            retryable: true,
            pendingOutcome: 'failed',
          });
        }, GEMINI_LIVE_SETUP_TIMEOUT_MS);
        const websocket = new WebSocket(
          resolveGeminiLiveWebSocketUrl(
            session.websocket_url,
            session.ephemeral_token,
          ),
        );
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
            typeof event.data !== 'string'
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
            if (setupTimerRef.current !== null) {
              window.clearTimeout(setupTimerRef.current);
              setupTimerRef.current = null;
            }
            if (!resumptionHandle && session.history) {
              sendWebSocketPayload(websocket, JSON.stringify(session.history));
            }
            setupReadyRef.current = true;
            reconnectingRef.current = false;
            const currentAttempt = attemptRef.current;
            if (currentAttempt?.generation === generation) {
              currentAttempt.serverVoiceState = 'listening';
              startSessionTimers(currentAttempt);
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
          if (ingest.audioTurnIndex !== null) {
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
            audioRef.current?.finishOutput(ingest.terminalTurnIndex);
            scheduleCommitFlush(generation);
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
          if (attemptRef.current?.generation !== generation) {
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
        .catch(() => {
          if (attemptRef.current?.generation === generation) {
            finishAttempt({
              reason: 'connection_error',
              keepOpen: true,
              errorCode: 'session_create_failed',
              retryable: true,
              pendingOutcome: 'failed',
            });
          }
        });
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
      trackSafely,
    ],
  );

  const retry = useCallback(() => {
    if (lastTargetRef.current) {
      start(lastTargetRef.current);
    }
  }, [start]);

  const toggleMuted = useCallback(() => {
    setViewState(previous => {
      const muted = !previous.muted;
      mutedRef.current = muted;
      audioRef.current?.setMuted(muted);
      if (muted) {
        sendWebSocketPayload(
          websocketRef.current,
          JSON.stringify({ realtimeInput: { audioStreamEnd: true } }),
        );
      }
      return { ...previous, muted };
    });
  }, []);

  const end = useCallback(() => {
    finishAttempt({ reason: 'user_end', keepOpen: false });
  }, [finishAttempt]);

  const close = useCallback(() => {
    finishAttempt({ reason: 'user_close', keepOpen: false });
  }, [finishAttempt]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && attemptRef.current) {
        finishAttempt({ reason: 'page_hidden', keepOpen: false });
      }
    };
    const handlePageHide = () => {
      if (attemptRef.current) {
        finishAttempt({ reason: 'page_hidden', keepOpen: false });
      }
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
  }, [finishAttempt, sessionScopeKey]);

  useEffect(() => {
    unmountedRef.current = false;
    return () => {
      unmountedRef.current = true;
      if (attemptRef.current) {
        finishAttemptRef.current?.({
          reason: 'lesson_changed',
          keepOpen: false,
        });
      }
    };
  }, []);

  return {
    ...viewState,
    start,
    retry,
    toggleMuted,
    end,
    close,
  };
};
