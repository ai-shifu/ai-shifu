import type {
  LiveFollowUpLearningMode,
  LiveFollowUpSurface,
} from '@/lib/liveVoiceFollowUp';

export const LIVE_VOICE_FOLLOW_UP_ATTEMPT_EVENT =
  'learner_voice_follow_up_attempt' as const;
export const LIVE_VOICE_FOLLOW_UP_RESULT_EVENT =
  'learner_voice_follow_up_result' as const;
export const LIVE_VOICE_FOLLOW_UP_SESSION_END_EVENT =
  'learner_voice_follow_up_session_end' as const;

export type LiveVoiceFollowUpOutcome = 'success' | 'failed' | 'cancelled';

export const LIVE_VOICE_FOLLOW_UP_ERROR_CODES = [
  'none',
  'microphone_denied',
  'microphone_unavailable',
  'microphone_busy',
  'audio_unavailable',
  'session_create_failed',
  'session_expired',
  'capacity_exceeded',
  'origin_rejected',
  'configuration_error',
  'network_error',
  'websocket_failed',
  'server_error',
  'unknown',
] as const;

export type LiveVoiceFollowUpErrorCode =
  (typeof LIVE_VOICE_FOLLOW_UP_ERROR_CODES)[number];

export const LIVE_VOICE_FOLLOW_UP_END_REASONS = [
  'user_end',
  'user_close',
  'timeout',
  'page_hidden',
  'lesson_changed',
  'connection_closed',
  'connection_error',
  'server_end',
  'server_timeout',
  'replaced',
] as const;

export type LiveVoiceFollowUpEndReason =
  (typeof LIVE_VOICE_FOLLOW_UP_END_REASONS)[number];

type LiveVoiceFollowUpBaseAnalyticsInput = {
  shifuBid: string;
  outlineBid: string;
  learningMode: LiveFollowUpLearningMode;
  surface: LiveFollowUpSurface;
};

export const shouldTrackLiveVoiceFollowUp = ({
  previewMode,
  learningMode,
}: {
  previewMode: boolean;
  learningMode: string;
}) => !previewMode && learningMode !== 'classroom';

export const normalizeLiveVoiceFollowUpErrorCode = (
  code: unknown,
): LiveVoiceFollowUpErrorCode => {
  const normalized = String(code || '').trim();
  const serverCodeAliases: Record<string, LiveVoiceFollowUpErrorCode> = {
    auth_failed: 'session_expired',
    capacity_reached: 'capacity_exceeded',
    connection_lost: 'network_error',
    feature_disabled: 'configuration_error',
    invalid_audio: 'audio_unavailable',
    invalid_control: 'configuration_error',
    lease_lost: 'server_error',
    persistence_failed: 'server_error',
    service_unavailable: 'server_error',
    upstream_ended: 'server_error',
    upstream_unavailable: 'server_error',
  };
  if (serverCodeAliases[normalized]) {
    return serverCodeAliases[normalized];
  }
  return (LIVE_VOICE_FOLLOW_UP_ERROR_CODES as readonly string[]).includes(
    normalized,
  )
    ? (normalized as LiveVoiceFollowUpErrorCode)
    : 'unknown';
};

export const normalizeLiveVoiceFollowUpEndReason = (
  reason: unknown,
): LiveVoiceFollowUpEndReason => {
  const normalized = String(reason || '').trim();
  return (LIVE_VOICE_FOLLOW_UP_END_REASONS as readonly string[]).includes(
    normalized,
  )
    ? (normalized as LiveVoiceFollowUpEndReason)
    : 'server_end';
};

export const buildLiveVoiceFollowUpAttemptAnalytics = ({
  shifuBid,
  outlineBid,
  learningMode,
  surface,
}: LiveVoiceFollowUpBaseAnalyticsInput) => ({
  shifu_bid: shifuBid,
  outline_bid: outlineBid,
  learning_mode: learningMode,
  surface,
});

export const buildLiveVoiceFollowUpResultAnalytics = ({
  shifuBid,
  outlineBid,
  learningMode,
  surface,
  outcome,
  errorCode,
}: LiveVoiceFollowUpBaseAnalyticsInput & {
  outcome: LiveVoiceFollowUpOutcome;
  errorCode: LiveVoiceFollowUpErrorCode;
}) => ({
  shifu_bid: shifuBid,
  outline_bid: outlineBid,
  learning_mode: learningMode,
  surface,
  outcome,
  error_code: errorCode,
});

export const buildLiveVoiceFollowUpSessionEndAnalytics = ({
  shifuBid,
  outlineBid,
  learningMode,
  surface,
  durationMs,
  hadExchange,
  endReason,
}: LiveVoiceFollowUpBaseAnalyticsInput & {
  durationMs: number;
  hadExchange: boolean;
  endReason: LiveVoiceFollowUpEndReason;
}) => {
  const normalizedDurationMs = Number.isFinite(durationMs)
    ? Math.max(0, Math.round(durationMs))
    : 0;
  return {
    shifu_bid: shifuBid,
    outline_bid: outlineBid,
    learning_mode: learningMode,
    surface,
    duration_ms: normalizedDurationMs,
    had_exchange: hadExchange,
    end_reason: endReason,
  };
};
