import request from '@/lib/request';

export const FOLLOW_UP_MODEL_CATALOG_API_PATH =
  '/api/llm/follow-up-model-list' as const;
export const LIVE_FOLLOW_UP_AUDIO_WORKLET_PATH =
  '/worklets/live-follow-up-audio.js' as const;
export const GEMINI_LIVE_INPUT_MIME_TYPE = 'audio/pcm;rate=16000' as const;
export const LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE = 4018;

const GEMINI_LIVE_WEBSOCKET_ORIGIN =
  'wss://generativelanguage.googleapis.com' as const;
const GEMINI_LIVE_CONSTRAINED_PATH =
  '/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained' as const;

export type FollowUpInteractionMode = 'text' | 'live_voice';
export type FollowUpBillingMode = 'billable' | 'free_preview';
export type FollowUpAllowedRole = 'main' | 'follow_up';

export type FollowUpVoice = {
  voice_id: string;
  style: string;
};

export type FollowUpModelCatalogItem = {
  model: string;
  display_name: string;
  credit_multiplier?: number | null;
  credit_multiplier_label?: string | null;
  is_default?: boolean;
  interaction_mode: FollowUpInteractionMode;
  allowed_roles: FollowUpAllowedRole[];
  billing_mode: FollowUpBillingMode;
  voices: FollowUpVoice[];
};

export type LiveFollowUpLearningMode = 'read' | 'listen';
export type LiveFollowUpSurface =
  | 'read_content'
  | 'listen_player'
  | 'teacher_preview';

export type LiveFollowUpSessionRequest = {
  anchor_element_bid: string;
  preview_mode: boolean;
  learning_mode: LiveFollowUpLearningMode;
  surface: LiveFollowUpSurface;
  operation?: 'create';
  request_bid?: string;
  replace_session_bid?: string;
  expected_admission_revision?: string;
};

export type LiveFollowUpControlReason =
  | 'capacity_exceeded'
  | 'ownership_conflict'
  | 'stale_request'
  | 'operation_conflict'
  | 'admission_unavailable'
  | 'pending'
  | 'response_lost';

export class LiveFollowUpControlError extends Error {
  readonly retryAfterMs?: number;

  constructor(
    readonly reason: LiveFollowUpControlReason,
    retryAfterMs?: number,
  ) {
    super('Live follow-up admission could not complete');
    this.name = 'LiveFollowUpControlError';
    this.retryAfterMs =
      typeof retryAfterMs === 'number' &&
      Number.isFinite(retryAfterMs) &&
      retryAfterMs > 0
        ? Math.min(Math.ceil(retryAfterMs), 60_000)
        : undefined;
  }
}

export type LiveFollowUpOperationResult = {
  request_bid: string;
  operation_status:
    | 'pending'
    | 'issued'
    | 'failed'
    | 'cancelled'
    | 'missing'
    | 'rejected';
  rotation_enabled: boolean;
  session_bid?: string;
  admission_revision?: string;
  ownership_current?: boolean;
  error_code?: Exclude<LiveFollowUpControlReason, 'pending' | 'response_lost'>;
  retry_after_ms?: number;
  server_time?: string;
};

export type GeminiLiveSetupMessage = {
  setup: Record<string, unknown>;
};

export type GeminiLiveHistoryMessage = {
  clientContent: {
    turns: Array<{
      role: 'user' | 'model';
      parts: Array<{ text: string }>;
    }>;
    turnComplete: true;
  };
};

export type LiveFollowUpSession = {
  session_bid: string;
  ephemeral_token: string;
  websocket_url: string;
  setup: GeminiLiveSetupMessage;
  history: GeminiLiveHistoryMessage | null;
  expires_at: string;
  new_session_expires_at: string;
  heartbeat_interval_ms: number;
  request_bid?: string;
  admission_revision?: string;
  operation_status?: 'issued';
  rotation_enabled?: boolean;
};

export type LiveFollowUpTurnReport = {
  turn_index: number;
  user_transcript: string;
  played_answer_transcript: string;
  interrupted: boolean;
  usage_metadata: Record<string, unknown> | null;
  latency_ms: number;
};

export type LiveFollowUpState =
  | 'connecting'
  | 'listening'
  | 'speaking'
  | 'reconnecting'
  | 'ended';

export type LiveFollowUpTranscriptRole = 'user' | 'assistant';

export type GeminiLiveServerEvent = {
  setupComplete: boolean;
  audioChunks: ArrayBuffer[];
  interimInputTranscripts: string[];
  inputTranscripts: string[];
  outputTranscripts: string[];
  interrupted: boolean;
  turnComplete: boolean;
  generationComplete: boolean;
  usageMetadata: Record<string, unknown> | null;
  resumptionHandle: string | null;
  resumable: boolean | null;
  goAway: boolean;
  upstreamError: boolean;
};

const liveFollowUpSessionPath = (sessionBid: string, action: string) =>
  `/api/learn/live-follow-up/session/${encodeURIComponent(sessionBid)}/${action}`;

export const createLiveFollowUpSession = (
  shifuBid: string,
  outlineBid: string,
  payload: LiveFollowUpSessionRequest,
): Promise<LiveFollowUpSession | LiveFollowUpOperationResult> => {
  const sessionPath = `/api/learn/shifu/${encodeURIComponent(shifuBid)}/live-follow-up/${encodeURIComponent(outlineBid)}/session`;
  return request.post(sessionPath, payload, {
    skipErrorToast: true,
    credentials: 'include',
  }) as Promise<LiveFollowUpSession | LiveFollowUpOperationResult>;
};

export const getLiveFollowUpOperationStatus = (
  shifuBid: string,
  outlineBid: string,
  requestBid: string,
  target: LiveFollowUpSessionRequest,
): Promise<LiveFollowUpOperationResult> =>
  request.post(
    `/api/learn/shifu/${encodeURIComponent(shifuBid)}/live-follow-up/${encodeURIComponent(outlineBid)}/session`,
    {
      operation: 'status',
      request_bid: requestBid,
      // Deliberately invalid as a legacy create: an old server must never mint
      // another credential when recovering a lost response via status lookup.
      target: {
        anchor_element_bid: target.anchor_element_bid,
        preview_mode: target.preview_mode,
        learning_mode: target.learning_mode,
        surface: target.surface,
        ...(target.replace_session_bid && {
          replace_session_bid: target.replace_session_bid,
        }),
        ...(target.expected_admission_revision && {
          expected_admission_revision: target.expected_admission_revision,
        }),
      },
    },
    { skipErrorToast: true, credentials: 'include' },
  ) as Promise<LiveFollowUpOperationResult>;

export const heartbeatLiveFollowUpSession = async (
  sessionBid: string,
): Promise<unknown> => {
  const result = (await request.post(
    liveFollowUpSessionPath(sessionBid, 'heartbeat'),
    {},
    { skipErrorToast: true, credentials: 'include' },
  )) as LiveFollowUpOperationResult | undefined;
  if (result?.operation_status === 'rejected') {
    throw new LiveFollowUpControlError(
      result.error_code ?? 'admission_unavailable',
      result.retry_after_ms,
    );
  }
  return result;
};

export type LiveFollowUpTurnAcknowledgement = {
  session_bid: string;
  turn_index: number;
  history_saved: boolean;
  ask_element_bid: string;
  answer_element_bid: string;
};

export const commitLiveFollowUpTurn = (
  sessionBid: string,
  payload: LiveFollowUpTurnReport,
): Promise<LiveFollowUpTurnAcknowledgement> =>
  request.post(liveFollowUpSessionPath(sessionBid, 'turn'), payload, {
    skipErrorToast: true,
    credentials: 'include',
  }) as Promise<LiveFollowUpTurnAcknowledgement>;

// Session creation has already resolved the runtime API URL. The shared
// keepalive path uses that cache to start fetch in the lifecycle callback itself.
export const finalizeLiveFollowUpSession = (
  sessionBid: string,
  turns: LiveFollowUpTurnReport[],
  reason: string,
): Promise<unknown> =>
  request.post(
    liveFollowUpSessionPath(sessionBid, 'finalize'),
    { turns, reason },
    { skipErrorToast: true, credentials: 'include', keepalive: true },
  );

export const endLiveFollowUpSession = (
  sessionBid: string,
  reason: string,
): Promise<unknown> =>
  request.post(
    liveFollowUpSessionPath(sessionBid, 'end'),
    { reason },
    { skipErrorToast: true, credentials: 'include', keepalive: true },
  );

export const getFollowUpModelCatalog = (): Promise<
  FollowUpModelCatalogItem[]
> =>
  request.get(FOLLOW_UP_MODEL_CATALOG_API_PATH, {
    skipErrorToast: true,
  }) as Promise<FollowUpModelCatalogItem[]>;

export const resolveGeminiLiveWebSocketUrl = (
  websocketUrl: string,
  ephemeralToken: string,
): string => {
  const url = new URL(websocketUrl);
  if (
    url.origin !== GEMINI_LIVE_WEBSOCKET_ORIGIN ||
    url.pathname !== GEMINI_LIVE_CONSTRAINED_PATH ||
    url.search ||
    url.hash ||
    !ephemeralToken.startsWith('auth_tokens/') ||
    ephemeralToken.length > 1024
  ) {
    throw new Error('Invalid Gemini Live session transport');
  }
  url.searchParams.set('access_token', ephemeralToken);
  return url.toString();
};

const readMapping = (
  source: Record<string, unknown> | null,
  ...keys: string[]
): Record<string, unknown> | null => {
  if (!source) {
    return null;
  }
  for (const key of keys) {
    const value = source[key];
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
  }
  return null;
};

const readValue = (
  source: Record<string, unknown> | null,
  ...keys: string[]
) => {
  if (!source) {
    return undefined;
  }
  for (const key of keys) {
    if (key in source) {
      return source[key];
    }
  }
  return undefined;
};

const transcriptFragments = (value: unknown): string[] => {
  if (typeof value === 'string') {
    return value ? [value] : [];
  }
  if (Array.isArray(value)) {
    return value.flatMap(transcriptFragments);
  }
  if (!value || typeof value !== 'object') {
    return [];
  }
  const text = (value as Record<string, unknown>).text;
  return typeof text === 'string' && text ? [text] : [];
};

const decodeBase64Audio = (value: string): ArrayBuffer | null => {
  try {
    const binary = window.atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes.buffer;
  } catch {
    return null;
  }
};

export const encodeGeminiLiveAudioMessage = (frame: ArrayBuffer): string => {
  const bytes = new Uint8Array(frame);
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return JSON.stringify({
    realtimeInput: {
      audio: {
        mimeType: GEMINI_LIVE_INPUT_MIME_TYPE,
        data: window.btoa(binary),
      },
    },
  });
};

export const parseGeminiLiveServerMessage = (
  payload: string | ArrayBuffer,
): GeminiLiveServerEvent | null => {
  let parsed: Record<string, unknown>;
  try {
    const text =
      typeof payload === 'string'
        ? payload
        : new TextDecoder('utf-8', { fatal: true }).decode(payload);
    const value = JSON.parse(text);
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return null;
    }
    parsed = value as Record<string, unknown>;
  } catch {
    return null;
  }

  const serverContent = readMapping(parsed, 'serverContent', 'server_content');
  const modelTurn = readMapping(serverContent, 'modelTurn', 'model_turn');
  const parts = Array.isArray(modelTurn?.parts) ? modelTurn.parts : [];
  const audioChunks: ArrayBuffer[] = [];
  for (const part of parts) {
    if (!part || typeof part !== 'object' || Array.isArray(part)) {
      continue;
    }
    const inlineData = readMapping(
      part as Record<string, unknown>,
      'inlineData',
      'inline_data',
    );
    const mimeType = String(
      inlineData?.mimeType || inlineData?.mime_type || '',
    ).toLowerCase();
    const encoded = inlineData?.data;
    if (!mimeType.startsWith('audio/pcm') || typeof encoded !== 'string') {
      continue;
    }
    const audio = decodeBase64Audio(encoded);
    if (!audio) {
      return null;
    }
    audioChunks.push(audio);
  }

  const resumption = readMapping(
    parsed,
    'sessionResumptionUpdate',
    'session_resumption_update',
  );
  const resumptionHandle =
    resumption?.newHandle || resumption?.new_handle || null;
  const resumable = resumption?.resumable;

  return {
    setupComplete: 'setupComplete' in parsed || 'setup_complete' in parsed,
    audioChunks,
    interimInputTranscripts: transcriptFragments(
      readValue(
        serverContent,
        'interimInputTranscription',
        'interim_input_transcription',
      ),
    ),
    inputTranscripts: transcriptFragments(
      readValue(serverContent, 'inputTranscription', 'input_transcription'),
    ),
    outputTranscripts: transcriptFragments(
      readValue(serverContent, 'outputTranscription', 'output_transcription'),
    ),
    interrupted: readValue(serverContent, 'interrupted') === true,
    turnComplete:
      readValue(serverContent, 'turnComplete', 'turn_complete') === true,
    generationComplete:
      readValue(serverContent, 'generationComplete', 'generation_complete') ===
      true,
    usageMetadata:
      readMapping(parsed, 'usageMetadata', 'usage_metadata') || null,
    resumptionHandle:
      typeof resumptionHandle === 'string' && resumptionHandle
        ? resumptionHandle
        : null,
    resumable: typeof resumable === 'boolean' ? resumable : null,
    goAway: Boolean(readMapping(parsed, 'goAway', 'go_away')),
    upstreamError: Boolean(readMapping(parsed, 'error')),
  };
};

export const mergeLiveTranscript = (current: string, incoming: string) => {
  if (!incoming || incoming === current || current.startsWith(incoming)) {
    return current;
  }
  if (!current || incoming.startsWith(current) || incoming.endsWith(current)) {
    return incoming;
  }
  const maximumOverlap = Math.min(current.length, incoming.length);
  for (let overlap = maximumOverlap; overlap > 0; overlap -= 1) {
    if (current.slice(-overlap) === incoming.slice(0, overlap)) {
      return current + incoming.slice(overlap);
    }
  }
  return current + incoming;
};
