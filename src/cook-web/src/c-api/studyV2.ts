import { SSE } from 'sse.js';
import request, { attachSseBusinessResponseFallback } from '@/lib/request';
import { v4 } from 'uuid';
import { getResolvedBaseURL } from '@/c-utils/envUtils';
import { useUserStore } from '@/store/useUserStore';
import {
  MockRunStreamFixtureSource,
  shouldUseMockStuckRunFixture,
} from './mockRunStreamFixture';

export const ELEMENT_TYPE = {
  INTERACTION: 'interaction',
  HTML: 'html',
  TEXT: 'text',
  TABLES: 'tables',
  CODE: 'code',
  LATEX: 'latex',
  MD_IMG: 'md_img',
  MERMAID: 'mermaid',
  TITLE: 'title',
  SVG: 'svg',
  DIFF: 'diff',
  IMG: 'img',
} as const;

export type ElementType = (typeof ELEMENT_TYPE)[keyof typeof ELEMENT_TYPE];

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
  ELEMENT: 'element',
  CONTENT: 'content',
  ERROR: 'error',
  BREAK: 'break',
  ASK: 'ask',
  TEXT_END: 'done',
  INTERACTION: 'interaction',
  OUTLINE_ITEM_UPDATE: 'outline_item_update',
  HEARTBEAT: 'heartbeat',
  VARIABLE_UPDATE: 'variable_update',
  PROFILE_UPDATE: 'update_user_info', // TODO: update user_info
  // Audio types for TTS
  AUDIO_SEGMENT: 'audio_segment',
  AUDIO_COMPLETE: 'audio_complete',
  NEW_SLIDE: 'new_slide',
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

export const LESSON_FEEDBACK_VARIABLE_NAME =
  'sys_lesson_feedback_score' as const;
export const LESSON_FEEDBACK_INTERACTION_MARKER =
  `%{{${LESSON_FEEDBACK_VARIABLE_NAME}}}` as const;

export interface SubtitleCueData {
  text: string;
  start_ms: number;
  end_ms: number;
  segment_index?: number;
  position?: number;
}

export interface StudyRecordAudioPayload {
  subtitle_cues?: SubtitleCueData[];
  [key: string]: unknown;
}

export interface StudyRecordPayload {
  audio?: StudyRecordAudioPayload;
  previous_visuals?: unknown[];
  user_input?: string;
  [key: string]: unknown;
}

export interface StudyRecordItem {
  element_type: ElementType;
  element_bid: string;
  element_index?: number;
  sequence_number?: number;
  target_element_bid?: string;
  change_type?: string;
  content: string;
  is_marker: boolean;
  is_new: boolean;
  is_renderable: boolean;
  is_speakable: boolean;
  like_status?: LikeStatus;
  generated_block_bid?: string;
  user_input?: string;
  payload?: StudyRecordPayload;
  isHistory?: boolean;
  audio_url?: string;
  audio_segments?: AudioSegmentData[];
}

export interface LessonStudyRecords {
  elements: StudyRecordItem[];
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

export interface SubmitLessonFeedbackParams {
  shifu_bid: string;
  outline_bid: string;
  score: number;
  comment?: string;
  mode?: 'read' | 'listen';
}

export interface SubmitLessonFeedbackResult {
  lesson_feedback_bid: string;
  shifu_bid: string;
  outline_bid: string;
  score: number;
  comment: string;
  mode: 'read' | 'listen';
}

// Audio types for TTS
export interface AudioSegmentData {
  segment_index: number;
  audio_data: string; // Base64 encoded
  duration_ms: number;
  is_final: boolean;
  position?: number;
  element_id?: string;
  slide_id?: string;
  av_contract?: Record<string, any> | null;
}

export interface AudioCompleteData {
  audio_url: string;
  audio_bid: string;
  duration_ms: number;
  position?: number;
  slide_id?: string;
  av_contract?: Record<string, any> | null;
}

export interface ListenSlideData {
  slide_id: string;
  element_bid?: string;
  target_element_bid?: string;
  generated_block_bid?: string;
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

const getListenFlagFromPageUrl = (): boolean => {
  if (typeof window === 'undefined') {
    return false;
  }

  const listenParam = new URLSearchParams(window.location.search).get('listen');
  return (
    typeof listenParam === 'string' && listenParam.toLowerCase() === 'true'
  );
};

const dispatchSseBusinessError = (
  source: { dispatchEvent: (event: Event) => void },
  error: { message: string; code?: number },
) => {
  const event = new CustomEvent('error');
  Object.assign(event, {
    detail: error,
    data: error.message,
    responseCode: error.code,
  });
  source.dispatchEvent(event);
};

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
  onError?: (error: unknown) => void,
) => {
  const token = useUserStore.getState().getToken();
  const payload = { ...body };
  payload.listen = Boolean(body.listen);

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

  if (shouldUseMockStuckRunFixture(body)) {
    const source = new MockRunStreamFixtureSource();

    source.addEventListener('message', event => {
      try {
        const response = JSON.parse((event as MessageEvent<string>).data);
        if (onMessage) {
          onMessage(response);
        }
      } catch {
        // ignore malformed SSE payloads
      }
    });

    source.addEventListener('error', e => {
      if (onError) {
        onError(e);
        return;
      }
      console.error('[Mock SSE error]', e);
    });

    source.stream();

    return source;
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
    if ((e as { detail?: unknown }).detail) {
      if (onError) {
        onError(e);
      }
      return;
    }

    if (onError) {
      onError(e);
      return;
    }
    console.error('[SSE error]', e);
  });

  attachSseBusinessResponseFallback(source, {
    requestToken: token || '',
    onHandled: error => {
      dispatchSseBusinessError(source, error);
    },
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

  attachSseBusinessResponseFallback(source, {
    requestToken: token || '',
    onHandled: error => {
      dispatchSseBusinessError(source, error);
    },
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
  const url = `${baseURL}/api/learn/shifu/${shifu_bid}/generated-blocks/${generated_block_bid}/tts?preview_mode=${preview_mode}&listen=${listen}`;
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
    .catch(() => {
      // when error, return empty records, go run api
      return {
        elements: [],
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

export const submitLessonFeedback = async (
  params: SubmitLessonFeedbackParams,
): Promise<SubmitLessonFeedbackResult> => {
  const { shifu_bid, outline_bid, ...payload } = params;
  return request.post(
    `/api/learn/shifu/${shifu_bid}/lesson-feedback/${outline_bid}`,
    payload,
  );
};
