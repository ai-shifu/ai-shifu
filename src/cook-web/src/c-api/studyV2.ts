import { SSE } from 'sse.js';
import request from '@/lib/request';
import { tokenStore } from '@/c-service/storeUtil';
import { v4 } from 'uuid';
import { getStringEnv } from '@/c-utils/envUtils';
import { useSystemStore } from '@/c-store/useSystemStore';
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
  TEXT_END: 'text_end',
  INTERACTION: 'interaction',
  OUTLINE_ITEM_UPDATE: 'outline_item_update',
  HEARTBEAT: 'heartbeat',
  VARIABLE_UPDATE: 'variable_update',
  PROFILE_UPDATE: 'update_user_info', // TODO: update user_info
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
}

export interface LessonStudyRecords {
  mdflow: string;
  records: StudyRecordItem[];
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

export const getRunMessage = (
  shifu_bid: string,
  outline_bid: string,
  preview_mode: boolean,
  body: { input: Record<string, any> | string; [key: string]: any },
  onMessage: (data: any) => void,
) => {
  const token = useUserStore.getState().getToken();
  const payload = { ...body };

  let baseURL = getStringEnv('baseURL');
  if (baseURL === '' || baseURL === '/') {
    baseURL = window.location.origin;
  }

  // TODO: MOCK
  payload.input = Object.values(body.input).join('');
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
      console.log('[SSE response]', response);
      if (onMessage) {
        onMessage(response);
      }
    } catch (e) {
      console.log(e);
    }
  });

  source.addEventListener('error', e => {
    console.error('[SSE error]', e);
  });

  // sse.js may not support 'close' event, use readystatechange instead
  source.addEventListener('readystatechange', () => {
    console.log('[SSE readystatechange]', source.readyState);
    // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
    if (source.readyState === 2) {
      console.log('[SSE connection close]');
    } else if (source.readyState === 1) {
      console.log('[SSE connection open]');
    }
  });

  source.stream();

  return source;
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
