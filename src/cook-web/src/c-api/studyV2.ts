import { SSE } from 'sse.js';
import request from '@/lib/request';
import { v4 } from 'uuid';
import { getResolvedBaseURL } from '@/c-utils/envUtils';
import { useUserStore } from '@/store/useUserStore';

// ===== Constants  Types for shared literals =====
// record history block type
export const BLOCK_TYPE = {
  CONTENT: 'content',
  INTERACTION: 'interaction',
  ASK: 'ask',
  ANSWER: 'answer',
  ERROR: 'error_message',
} as const;
export type BlockType = (typeof BLOCK_TYPE)[keyof typeof BLOCK_TYPE];

export const LIKE_STATUS = {
  LIKE: 'like',
  DISLIKE: 'dislike',
  NONE: 'none',
} as const;
export type LikeStatus = (typeof LIKE_STATUS)[keyof typeof LIKE_STATUS];

export const SSE_INPUT_TYPE = {
  NORMAL: 'normal',
  ASK: 'ask',
} as const;
export type SSE_INPUT_TYPE =
  (typeof SSE_INPUT_TYPE)[keyof typeof SSE_INPUT_TYPE];

// export const PREVIEW_MODE = {
//   COOK: 'cook',
//   PREVIEW: 'preview',
//   NORMAL: 'normal',
// } as const;
// export type PreviewMode = (typeof PREVIEW_MODE)[keyof typeof PREVIEW_MODE];

export const LEARNING_PERMISSION = {
  NORMAL: 'normal',
  TRIAL: 'trial',
  GUEST: 'guest',
} as const;
export type LearningPermission =
  (typeof LEARNING_PERMISSION)[keyof typeof LEARNING_PERMISSION];

// run sse output type
export const SSE_OUTPUT_TYPE = {
  CONTENT: 'content',
  BREAK: 'break',
  ASK: 'ask',
  TEXT_END: 'done',
  INTERACTION: 'interaction',
  OUTLINE_ITEM_UPDATE: 'outline_item_update',
  HEARTBEAT: 'heartbeat',
  VARIABLE_UPDATE: 'variable_update',
  PROFILE_UPDATE: 'update_user_info', // TODO: update user_info
  // Audio types for TTS
  NEW_SLIDE: 'new_slide',
  AUDIO_SEGMENT: 'audio_segment',
  AUDIO_COMPLETE: 'audio_complete',
} as const;
export type SSE_OUTPUT_TYPE =
  (typeof SSE_OUTPUT_TYPE)[keyof typeof SSE_OUTPUT_TYPE];

export const SYS_INTERACTION_TYPE = {
  PAY: '_sys_pay',
  LOGIN: '_sys_login',
  NEXT_CHAPTER: '_sys_next_chapter',
} as const;
export type SysInteractionType =
  (typeof SYS_INTERACTION_TYPE)[keyof typeof SYS_INTERACTION_TYPE];

export interface StudyRecordItem {
  block_type: BlockType;
  content: string;
  generated_block_bid: string;
  like_status?: LikeStatus;
  user_input?: string;
  isHistory?: boolean;
  audio_url?: string;
  audios?: AudioCompleteData[];
  av_contract?: AvContractData;
}

export interface LessonStudyRecords {
  mdflow: string;
  records: StudyRecordItem[];
  slides?: ListenSlideData[];
}

export interface GetLessonStudyRecordParams {
  shifu_bid: string;
  outline_bid: string;
  // Optional preview mode flag
  preview_mode?: boolean;
}

export interface PostGeneratedContentActionParams {
  shifu_bid: string;
  generated_block_bid: string;
  action: LikeStatus;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface PostGeneratedContentActionData {
  shifu_bid: string;
  generated_block_bid: string;
  action: LikeStatus;
}

export interface RunningResult {
  is_running: boolean;
  running_time: number;
}

// Audio types for TTS
export interface AvVisualBoundaryData {
  kind: string;
  position: number;
  block_bid: string;
  source_span: number[];
}

export interface AvSpeakableSegmentData {
  position: number;
  text: string;
  after_visual_kind: string;
  block_bid: string;
  source_span: number[];
}

export interface AvContractData {
  visual_boundaries: AvVisualBoundaryData[];
  speakable_segments: AvSpeakableSegmentData[];
}

export interface AudioSegmentData {
  segment_index: number;
  audio_data: string; // Base64 encoded
  duration_ms: number;
  is_final: boolean;
  position?: number;
  slide_id?: string;
  av_contract?: AvContractData;
}

export interface AudioCompleteData {
  audio_url: string;
  audio_bid: string;
  duration_ms: number;
  position?: number;
  slide_id?: string;
  av_contract?: AvContractData;
}

export interface ListenSlideData {
  slide_id: string;
  generated_block_bid: string;
  slide_index: number;
  audio_position: number;
  visual_kind: string;
  segment_type: string;
  segment_content: string;
  source_span: number[];
  is_placeholder: boolean;
}

export interface StreamGeneratedBlockAudioParams {
  shifu_bid: string;
  generated_block_bid: string;
  preview_mode?: boolean;
  listen?: boolean;
  onMessage: (data: any) => void;
  onError?: (error: unknown) => void;
}

export const getRunMessage = (
  shifu_bid: string,
  outline_bid: string,
  preview_mode: boolean,
  body: {
    input: Record<string, any> | string;
    listen?: boolean;
    [key: string]: any;
  },
  onMessage: (data: any) => void,
) => {
  const token = useUserStore.getState().getToken();
  const payload = { ...body };

  const baseURL = getResolvedBaseURL();

  // Convert input values to array format for markdown-flow 0.2.27+
  // Backend expects: { "variableName": ["value1", "value2"] }
  if (typeof body.input === 'object' && body.input !== null) {
    payload.input = Object.fromEntries(
      Object.entries(body.input).map(([key, value]) => [
        key,
        Array.isArray(value) ? value : [value],
      ]),
    );
  } else if (typeof body.input === 'string') {
    // If input is string, use default 'input' as key
    payload.input = { input: [body.input] };
  }
  const source = new SSE(
    `${baseURL}/api/learn/shifu/${shifu_bid}/run/${outline_bid}?preview_mode=${preview_mode}`,
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': v4().replace(/-/g, ''),
        Authorization: `Bearer ${token}`,
        Token: token,
      },
      payload: JSON.stringify(payload),
      method: 'PUT',
    },
  );

  source.addEventListener('message', event => {
    try {
      const response = JSON.parse(event.data);
      if (onMessage) {
        onMessage(response);
      }
    } catch {
      // ignore malformed SSE payloads
    }
  });

  source.addEventListener('error', e => {
    console.error('[SSE error]', e);
  });

  source.stream();

  return source;
};

const createSseSource = (
  url: string,
  payload: Record<string, unknown>,
  onMessage: (data: any) => void,
  onError?: (error: unknown) => void,
) => {
  const token = useUserStore.getState().getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Request-ID': v4().replace(/-/g, ''),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
    headers.Token = token;
  }

  const source = new SSE(url, {
    headers,
    payload: JSON.stringify(payload),
    method: 'POST',
  });

  source.addEventListener('message', event => {
    try {
      const response = JSON.parse(event.data);
      onMessage(response);
    } catch {
      // ignore malformed SSE payloads
    }
  });

  source.addEventListener('error', e => {
    onError?.(e);
  });

  source.stream();

  return source;
};

export const streamGeneratedBlockAudio = ({
  shifu_bid,
  generated_block_bid,
  preview_mode = false,
  listen = false,
  onMessage,
  onError,
}: StreamGeneratedBlockAudioParams) => {
  const baseURL = getResolvedBaseURL();
  const url = `${baseURL}/api/learn/shifu/${shifu_bid}/generated-blocks/${generated_block_bid}/tts?preview_mode=${preview_mode}${listen ? '&listen=true' : ''}`;
  return createSseSource(url, {}, onMessage, onError);
};

/**
 * Fetch course study records
 * @param {*} lessonId
 *  shifu_bid : shifu bid
    outline_bid: outline bid
    preview_mode: whether preview mode is enabled; possible values: cook | preview | normal (default is normal)
 * @returns
 */
export const getLessonStudyRecord = async ({
  shifu_bid,
  outline_bid,
  preview_mode = false,
}: GetLessonStudyRecordParams): Promise<LessonStudyRecords> => {
  return request
    .get(
      `/api/learn/shifu/${shifu_bid}/records/${outline_bid}?preview_mode=${preview_mode}`,
    )
    .catch(error => {
      // when error, return empty records, go run api
      return {
        records: [],
      };
    });
};

/**
 * Like or dislike generated content
 * shifu_bid: shifu bid
 * generated_block_bid: generated content bid
 * action: action like | dislike | none
 * @param params
 * @returns
 */
export async function postGeneratedContentAction(
  params: PostGeneratedContentActionParams,
): Promise<PostGeneratedContentActionData> {
  const { shifu_bid, generated_block_bid, action } = params;
  const url = `/api/learn/shifu/${shifu_bid}/generated-contents/${generated_block_bid}/${action}`;
  // Use standard request wrapper; it will return response.data when code===0
  return request.post(url, params);
}

export const checkIsRunning = async (
  shifu_bid: string,
  outline_bid: string,
): Promise<RunningResult> => {
  const url = `/api/learn/shifu/${shifu_bid}/run/${outline_bid}`;
  return request.get(url);
};
