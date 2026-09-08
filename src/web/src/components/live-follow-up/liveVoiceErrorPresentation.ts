import type { I18nKey } from '@/types/i18n-keys';
import type { LiveVoiceFollowUpErrorCode } from './liveVoiceFollowUpAnalytics';
import type { LiveVoiceErrorDiagnostic } from './useLiveVoiceFollowUp';

const errorMessages = {
  microphone_denied: 'module.chat.liveVoiceErrors.microphone_denied',
  microphone_unavailable: 'module.chat.liveVoiceErrors.microphone_unavailable',
  microphone_busy: 'module.chat.liveVoiceErrors.microphone_busy',
  audio_unavailable: 'module.chat.liveVoiceErrors.audio_unavailable',
  session_create_failed: 'module.chat.liveVoiceErrors.session_create_failed',
  session_expired: 'module.chat.liveVoiceErrors.session_expired',
  capacity_exceeded: 'module.chat.liveVoiceErrors.capacity_exceeded',
  origin_rejected: 'module.chat.liveVoiceErrors.origin_rejected',
  configuration_error: 'module.chat.liveVoiceErrors.configuration_error',
  network_error: 'module.chat.liveVoiceErrors.network_error',
  websocket_failed: 'module.chat.liveVoiceErrors.websocket_failed',
  server_error: 'module.chat.liveVoiceErrors.server_error',
  unknown: 'module.chat.liveVoiceErrors.unknown',
  ownership_conflict: 'module.chat.liveVoiceErrors.ownership_conflict',
  stale_request: 'module.chat.liveVoiceErrors.stale_request',
  operation_conflict: 'module.chat.liveVoiceErrors.operation_conflict',
  admission_unavailable: 'module.chat.liveVoiceErrors.admission_unavailable',
  pending: 'module.chat.liveVoiceErrors.pending',
  response_lost: 'module.chat.liveVoiceErrors.response_lost',
} satisfies Record<
  | Exclude<LiveVoiceFollowUpErrorCode, 'none'>
  | NonNullable<LiveVoiceErrorDiagnostic['reason']>,
  I18nKey
>;

const stageMessages = {
  session_create: 'module.chat.liveVoiceErrorStages.session_create',
  resume: 'module.chat.liveVoiceErrorStages.resume',
  heartbeat: 'module.chat.liveVoiceErrorStages.heartbeat',
  websocket: 'module.chat.liveVoiceErrorStages.websocket',
} satisfies Record<LiveVoiceErrorDiagnostic['stage'], I18nKey>;

/** Only bounded machine codes can enter presentation; never render raw errors. */
export const liveVoiceErrorPresentation = (
  error: unknown,
  diagnostic?: LiveVoiceErrorDiagnostic | null,
) => {
  const candidate = diagnostic?.reason ?? error;
  const code =
    typeof candidate === 'string' && Object.hasOwn(errorMessages, candidate)
      ? (candidate as keyof typeof errorMessages)
      : 'unknown';
  const closeCode = diagnostic?.websocketCloseCode;
  return {
    code,
    messageKey: errorMessages[code],
    stageKey:
      diagnostic && Object.hasOwn(stageMessages, diagnostic.stage)
        ? stageMessages[diagnostic.stage]
        : null,
    closeCode:
      typeof closeCode === 'number' &&
      Number.isInteger(closeCode) &&
      closeCode >= 1000 &&
      closeCode <= 4999
        ? closeCode
        : null,
  };
};
