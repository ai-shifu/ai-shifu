'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { useTracking } from '@/c-common/hooks/useTracking';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import {
  createLiveFollowUpSession,
  parseLiveFollowUpServerMessage,
  resolveLiveFollowUpWebSocketUrl,
  type LiveFollowUpLearningMode,
  type LiveFollowUpState,
  type LiveFollowUpSurface,
  type LiveFollowUpTranscriptRole,
} from '@/lib/liveVoiceFollowUp';

import {
  buildLiveVoiceFollowUpAttemptAnalytics,
  buildLiveVoiceFollowUpResultAnalytics,
  buildLiveVoiceFollowUpSessionEndAnalytics,
  normalizeLiveVoiceFollowUpEndReason,
  normalizeLiveVoiceFollowUpErrorCode,
  shouldTrackLiveVoiceFollowUp,
  LIVE_VOICE_FOLLOW_UP_ATTEMPT_EVENT,
  LIVE_VOICE_FOLLOW_UP_RESULT_EVENT,
  LIVE_VOICE_FOLLOW_UP_SESSION_END_EVENT,
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
// Keep at most 250 ms of 16 kHz mono PCM16 queued in the browser. Frames
// captured while the uplink is stalled are dropped so recovery cannot burst
// enough stale audio to trip the server's real-time input limiter.
const MAX_BUFFERED_INPUT_AUDIO_BYTES = 8 * 1024;

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

const sendWebSocketPayload = (
  websocket: WebSocket | null,
  payload: string | ArrayBuffer,
) => {
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

const sendInputAudioFrame = (
  websocket: WebSocket | null,
  frame: ArrayBuffer,
) => {
  if (
    websocket?.readyState !== WebSocket.OPEN ||
    websocket.bufferedAmount + frame.byteLength > MAX_BUFFERED_INPUT_AUDIO_BYTES
  ) {
    return false;
  }
  return sendWebSocketPayload(websocket, frame);
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
  const audioRef = useRef<LiveVoiceFollowUpAudio | null>(null);
  const mutedRef = useRef(false);
  const outputTurnIndexRef = useRef<number | null>(null);
  const reconnectingRef = useRef(false);
  const transcriptsRef = useRef<LiveVoiceTranscript[]>([]);
  const committedTurnIndexesRef = useRef<Set<number>>(new Set());
  const warningTimerRef = useRef<number | null>(null);
  const timeoutTimerRef = useRef<number | null>(null);
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
    if (warningTimerRef.current !== null) {
      window.clearTimeout(warningTimerRef.current);
      warningTimerRef.current = null;
    }
    if (timeoutTimerRef.current !== null) {
      window.clearTimeout(timeoutTimerRef.current);
      timeoutTimerRef.current = null;
    }
  }, []);

  const teardownTransport = useCallback(
    ({ sendEndControl = false }: { sendEndControl?: boolean } = {}) => {
      clearTimers();
      const websocket = websocketRef.current;
      websocketRef.current = null;
      if (websocket) {
        websocket.onopen = null;
        websocket.onmessage = null;
        websocket.onerror = null;
        websocket.onclose = null;
      }
      const closeWebSocket = () => {
        if (!websocket) {
          return;
        }
        if (sendEndControl) {
          sendWebSocketPayload(websocket, JSON.stringify({ type: 'end' }));
        }
        if (
          websocket.readyState === WebSocket.OPEN ||
          websocket.readyState === WebSocket.CONNECTING
        ) {
          websocket.close(1000, 'session ended');
        }
      };
      const audio = audioRef.current;
      audioRef.current = null;
      if (audio) {
        // `stop` waits for the worklet's bounded playback-progress flush ACK.
        // Keep this attempt's socket open until that checkpoint and the final
        // end control have been sent.
        void audio
          .stop()
          .catch(() => {})
          .finally(closeWebSocket);
      } else {
        closeWebSocket();
      }
      outputTurnIndexRef.current = null;
      reconnectingRef.current = false;
      releaseExclusive();
    },
    [clearTimers, releaseExclusive],
  );

  const finishAttempt = useCallback(
    ({
      reason,
      keepOpen,
      errorCode = null,
      retryable = false,
      pendingOutcome = 'cancelled',
      sendEndControl = false,
    }: {
      reason: LiveVoiceFollowUpEndReason;
      keepOpen: boolean;
      errorCode?: LiveVoiceFollowUpErrorCode | null;
      retryable?: boolean;
      pendingOutcome?: LiveVoiceFollowUpOutcome;
      sendEndControl?: boolean;
    }) => {
      const attempt = attemptRef.current;
      teardownTransport({ sendEndControl });
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
  const finishAttemptRef = useRef(finishAttempt);
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
      reconnectingRef.current = false;
      transcriptsRef.current = [];
      committedTurnIndexesRef.current.clear();

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
      });

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

      let attemptWebSocket: WebSocket | null = null;

      const startServerDeadlineIfNeeded = (currentAttempt: ActiveAttempt) => {
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

      // Both operations are deliberately launched synchronously from the
      // button handler. In particular, microphone permission and
      // AudioContext.resume() must not wait for the HTTP response.
      let audioPromise: Promise<LiveVoiceFollowUpAudio>;
      try {
        audioPromise = LiveVoiceFollowUpAudio.activate({
          onInputFrame: frame => {
            const currentAttempt = attemptRef.current;
            if (
              currentAttempt?.generation === generation &&
              currentAttempt.serverVoiceState !== null
            ) {
              sendInputAudioFrame(websocketRef.current, frame);
            }
          },
          onPlaybackProgress: (turnIndex, playedBytes) => {
            sendWebSocketPayload(
              attemptWebSocket,
              JSON.stringify({
                type: 'playback_progress',
                turn_index: turnIndex,
                played_bytes: playedBytes,
              }),
            );
          },
          onPlaybackComplete: turnIndex => {
            sendWebSocketPayload(
              attemptWebSocket,
              JSON.stringify({
                type: 'playback_complete',
                turn_index: turnIndex,
              }),
            );
          },
        });
      } catch (error) {
        audioPromise = Promise.reject(error);
      }
      void audioPromise
        .then(audio => {
          if (attemptRef.current?.generation !== generation) {
            void audio.stop().catch(() => {});
            return;
          }
          // Retain the live audio graph as soon as activation succeeds. The
          // session POST may still be pending, but close/hide/scope changes
          // must be able to stop the microphone immediately.
          audioRef.current = audio;
          audio.setMuted(mutedRef.current);
          attemptRef.current.audioActivated = true;
          markConnectedIfReady();
        })
        .catch(error => {
          if (attemptRef.current?.generation !== generation) {
            return;
          }
          finishAttempt({
            reason: 'connection_error',
            keepOpen: true,
            errorCode: resolveActivationErrorCode(error),
            retryable: true,
            pendingOutcome: 'failed',
          });
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

      // Consume the one-time ticket as soon as the POST resolves. A microphone
      // permission prompt can remain open longer than the ticket TTL, so the
      // WebSocket setup must not wait for audio activation.
      void sessionPromise
        .then(session => {
          if (attemptRef.current?.generation !== generation) {
            return;
          }
          const websocket = new WebSocket(
            resolveLiveFollowUpWebSocketUrl(session.ws_path),
          );
          attemptWebSocket = websocket;
          websocket.binaryType = 'arraybuffer';
          websocketRef.current = websocket;

          websocket.onopen = () => {
            const currentAttempt = attemptRef.current;
            if (currentAttempt?.generation !== generation) {
              websocket.close();
            }
          };

          websocket.onmessage = event => {
            if (attemptRef.current?.generation !== generation) {
              return;
            }
            if (event.data instanceof ArrayBuffer) {
              const turnIndex = outputTurnIndexRef.current;
              if (turnIndex !== null) {
                audioRef.current?.enqueueOutput(event.data, turnIndex);
              }
              return;
            }
            if (typeof event.data !== 'string') {
              return;
            }
            const message = parseLiveFollowUpServerMessage(event.data);
            if (!message) {
              return;
            }
            switch (message.type) {
              case 'state':
                const isResumeHandshakeListening =
                  message.state === 'listening' && reconnectingRef.current;
                if (message.state === 'reconnecting') {
                  reconnectingRef.current = true;
                } else if (message.state === 'listening') {
                  reconnectingRef.current = false;
                }
                if (
                  message.state === 'listening' ||
                  message.state === 'speaking'
                ) {
                  const currentAttempt = attemptRef.current;
                  if (currentAttempt?.generation === generation) {
                    currentAttempt.serverVoiceState = message.state;
                    startServerDeadlineIfNeeded(currentAttempt);
                    markConnectedIfReady();
                  }
                } else if (attemptRef.current?.generation === generation) {
                  attemptRef.current.serverVoiceState = null;
                }
                if (
                  message.state === 'speaking' &&
                  typeof message.turn_index === 'number'
                ) {
                  outputTurnIndexRef.current = message.turn_index;
                }
                if (message.state === 'listening') {
                  const completedTurnIndex = outputTurnIndexRef.current;
                  if (
                    completedTurnIndex !== null &&
                    !isResumeHandshakeListening
                  ) {
                    audioRef.current?.finishOutput(completedTurnIndex);
                  }
                  if (!isResumeHandshakeListening) {
                    outputTurnIndexRef.current = null;
                  }
                }
                if (
                  message.state !== 'listening' &&
                  message.state !== 'speaking'
                ) {
                  setViewState(previous => ({
                    ...previous,
                    state: message.state,
                  }));
                } else if (attemptRef.current?.connectedAt !== null) {
                  setViewState(previous => ({
                    ...previous,
                    state: message.state,
                  }));
                }
                break;
              case 'transcript':
                if (message.role === 'assistant') {
                  outputTurnIndexRef.current = message.turn_index;
                }
                transcriptsRef.current = sortTranscripts([
                  ...transcriptsRef.current.filter(
                    transcript =>
                      transcript.turnIndex !== message.turn_index ||
                      transcript.role !== message.role,
                  ),
                  {
                    role: message.role,
                    turnIndex: message.turn_index,
                    text: message.text,
                    final: message.final,
                  },
                ]);
                setViewState(previous => {
                  return {
                    ...previous,
                    transcripts: transcriptsRef.current,
                  };
                });
                break;
              case 'interrupted':
                audioRef.current?.clearPlayback();
                outputTurnIndexRef.current = null;
                setViewState(previous => ({
                  ...previous,
                  state: 'listening',
                }));
                break;
              case 'turn_committed':
                if (attemptRef.current) {
                  attemptRef.current.hadExchange = true;
                  if (
                    !committedTurnIndexesRef.current.has(message.turn_index)
                  ) {
                    committedTurnIndexesRef.current.add(message.turn_index);
                    const turnTranscripts = transcriptsRef.current.filter(
                      transcript => transcript.turnIndex === message.turn_index,
                    );
                    try {
                      onTurnCommitted?.({
                        anchorElementBid: attemptRef.current.anchorElementBid,
                        turnIndex: message.turn_index,
                        userTranscript:
                          turnTranscripts.find(
                            transcript => transcript.role === 'user',
                          )?.text ?? '',
                        assistantTranscript:
                          turnTranscripts.find(
                            transcript => transcript.role === 'assistant',
                          )?.text ?? '',
                      });
                    } catch {}
                  }
                }
                break;
              case 'error': {
                const errorCode = normalizeLiveVoiceFollowUpErrorCode(
                  message.code,
                );
                finishAttempt({
                  reason: 'connection_error',
                  keepOpen: true,
                  errorCode,
                  retryable: message.retryable,
                  pendingOutcome: 'failed',
                });
                break;
              }
              case 'session_end': {
                const endedBeforeConnection =
                  attemptRef.current?.connectedAt === null;
                finishAttempt({
                  reason: normalizeLiveVoiceFollowUpEndReason(message.reason),
                  keepOpen: true,
                  retryable: true,
                  errorCode: endedBeforeConnection ? 'server_error' : null,
                  pendingOutcome: endedBeforeConnection
                    ? 'failed'
                    : 'cancelled',
                });
                break;
              }
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
        })
        .catch(() => {
          if (attemptRef.current?.generation !== generation) {
            return;
          }
          finishAttempt({
            reason: 'connection_error',
            keepOpen: true,
            errorCode: 'session_create_failed',
            retryable: true,
            pendingOutcome: 'failed',
          });
        });
    },
    [
      analyticsEnabled,
      finishAttempt,
      learningMode,
      onTurnCommitted,
      outlineBid,
      previewMode,
      reportAttemptResult,
      requestExclusive,
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
          JSON.stringify({ type: 'audio_stream_end' }),
        );
      }
      return { ...previous, muted };
    });
  }, []);

  const end = useCallback(() => {
    finishAttempt({
      reason: 'user_end',
      keepOpen: false,
      sendEndControl: true,
    });
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
        finishAttemptRef.current({
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
