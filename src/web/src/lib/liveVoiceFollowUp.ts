import request from '@/lib/request';
import { getResolvedBaseURL } from '@/c-utils/envUtils';

export const FOLLOW_UP_MODEL_CATALOG_API_PATH =
  '/api/llm/follow-up-model-list' as const;
export const LIVE_FOLLOW_UP_AUDIO_WORKLET_PATH =
  '/worklets/live-follow-up-audio.js' as const;

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
};

export type LiveFollowUpSession = {
  session_bid: string;
  ws_path: string;
  expires_at: string;
};

export type LiveFollowUpState =
  | 'connecting'
  | 'listening'
  | 'speaking'
  | 'reconnecting'
  | 'ended';

export type LiveFollowUpTranscriptRole = 'user' | 'assistant';

export type LiveFollowUpServerMessage =
  | {
      type: 'state';
      state: LiveFollowUpState;
      turn_index?: number;
    }
  | {
      type: 'transcript';
      role: LiveFollowUpTranscriptRole;
      turn_index: number;
      text: string;
      final: boolean;
    }
  | {
      type: 'interrupted';
      turn_index?: number;
    }
  | {
      type: 'turn_committed';
      turn_index: number;
    }
  | {
      type: 'error';
      code: string;
      retryable: boolean;
    }
  | {
      type: 'session_end';
      reason: string;
    };

export const createLiveFollowUpSession = (
  shifuBid: string,
  outlineBid: string,
  payload: LiveFollowUpSessionRequest,
): Promise<LiveFollowUpSession> =>
  request.post(
    `/api/learn/shifu/${encodeURIComponent(shifuBid)}/live-follow-up/${encodeURIComponent(outlineBid)}/session`,
    payload,
    { skipErrorToast: true, credentials: 'include' },
  ) as Promise<LiveFollowUpSession>;

export const getFollowUpModelCatalog = (): Promise<
  FollowUpModelCatalogItem[]
> =>
  request.get(FOLLOW_UP_MODEL_CATALOG_API_PATH, {
    skipErrorToast: true,
  }) as Promise<FollowUpModelCatalogItem[]>;

export const resolveLiveFollowUpWebSocketUrl = (wsPath: string): string => {
  const apiBaseUrl = getResolvedBaseURL();
  const fallbackBaseUrl =
    typeof window !== 'undefined' ? window.location.origin : '';
  const baseUrl = new URL(apiBaseUrl || fallbackBaseUrl);
  const url = new URL(wsPath, baseUrl);
  if (
    !url.pathname.startsWith('/api/learn/live-follow-up/ws/') ||
    url.origin !== baseUrl.origin
  ) {
    throw new Error('Invalid live follow-up WebSocket path');
  }
  if (url.protocol === 'https:') {
    url.protocol = 'wss:';
  } else if (url.protocol === 'http:') {
    url.protocol = 'ws:';
  }
  return url.toString();
};

const isTranscriptRole = (
  value: unknown,
): value is LiveFollowUpTranscriptRole =>
  value === 'user' || value === 'assistant';

const isLiveState = (value: unknown): value is LiveFollowUpState =>
  value === 'connecting' ||
  value === 'listening' ||
  value === 'speaking' ||
  value === 'reconnecting' ||
  value === 'ended';

export const parseLiveFollowUpServerMessage = (
  payload: string,
): LiveFollowUpServerMessage | null => {
  let parsed: Record<string, unknown>;
  try {
    const value = JSON.parse(payload);
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return null;
    }
    parsed = value as Record<string, unknown>;
  } catch {
    return null;
  }

  switch (parsed.type) {
    case 'state':
      return isLiveState(parsed.state)
        ? {
            type: 'state',
            state: parsed.state,
            ...(Number.isInteger(parsed.turn_index)
              ? { turn_index: Number(parsed.turn_index) }
              : {}),
          }
        : null;
    case 'transcript':
      return isTranscriptRole(parsed.role) &&
        Number.isInteger(parsed.turn_index) &&
        typeof parsed.text === 'string' &&
        typeof parsed.final === 'boolean'
        ? {
            type: 'transcript',
            role: parsed.role,
            turn_index: Number(parsed.turn_index),
            text: parsed.text,
            final: parsed.final,
          }
        : null;
    case 'interrupted':
      return {
        type: 'interrupted',
        ...(Number.isInteger(parsed.turn_index)
          ? { turn_index: Number(parsed.turn_index) }
          : {}),
      };
    case 'turn_committed':
      return Number.isInteger(parsed.turn_index)
        ? {
            type: 'turn_committed',
            turn_index: Number(parsed.turn_index),
          }
        : null;
    case 'error':
      return typeof parsed.code === 'string' &&
        typeof parsed.retryable === 'boolean'
        ? {
            type: 'error',
            code: parsed.code,
            retryable: parsed.retryable,
          }
        : null;
    case 'session_end':
      return typeof parsed.reason === 'string'
        ? { type: 'session_end', reason: parsed.reason }
        : null;
    default:
      return null;
  }
};
