import { SSE } from 'sse.js';
import request from '@/lib/request';
import { tokenStore } from '@/c-service/storeUtil';
import { v4 } from 'uuid';
import { getStringEnv } from '@/c-utils/envUtils';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useUserStore } from '@/store/useUserStore';

// ===== Constants + Types for shared literals =====
export const BLOCK_TYPE = {
  CONTENT: 'content',
  INTERACTION: 'interaction',
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
export type SSE_INPUT_TYPE = (typeof SSE_INPUT_TYPE)[keyof typeof SSE_INPUT_TYPE];

export const PREVIEW_MODE = {
  COOK: 'cook',
  PREVIEW: 'preview',
  NORMAL: 'normal',
} as const;
export type PreviewMode = (typeof PREVIEW_MODE)[keyof typeof PREVIEW_MODE];

export const SSE_OUTPUT_TYPE = {
    CONTENT: 'content',
    BREAK: 'break',
    INTERACTION: 'interaction',
    OUTLINE_ITEM_UPDATE: 'outline_item_update',
    PROFILE_UPDATE: 'update_user_info', // TODO: update user_info
} as const;
export type SSE_OUTPUT_TYPE = (typeof SSE_OUTPUT_TYPE)[keyof typeof SSE_OUTPUT_TYPE];

export const SYS_INTERACTION_TYPE = {
  PAY: '_sys_pay',
  LOGIN: '_sys_login',
  NEXT_CHAPTER: '_sys_next_chapter', // TODO: wait for backend to support
} as const;
export type SysInteractionType = (typeof SYS_INTERACTION_TYPE)[keyof typeof SYS_INTERACTION_TYPE];


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
  preview_mode?: PreviewMode;
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

export const getRunMessage = (
  shifu_bid,
  outline_bid,
  preview_mode = PREVIEW_MODE.NORMAL,
  body,
  onMessage,
) => {
  const token = useUserStore.getState().getToken();

  let baseURL = getStringEnv('baseURL');
  if (baseURL === '' || baseURL === '/') {
    baseURL = window.location.origin;
  }

  // TODO: MOCK
  body.input = Object.values(body.input).join('');
  const source = new SSE(
    `${baseURL}/api/learn/shifu/${shifu_bid}/run/${outline_bid}?preview_mode=${preview_mode}`,
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': v4().replace(/-/g, ''),
        Authorization: `Bearer ${token}`,
        Token: token,
      },
      payload: JSON.stringify(body),
      method: 'PUT',
    },
  );

  // 先mock以前老的数据，后续再替换为新的数据

  // const source = new SSE(
  //   `${baseURL}/api/study/run?preview_mode=false&token=${tokenStore.get()}`,
  //   {
  //     headers: {
  //       'Content-Type': 'application/json',
  //       'X-Request-ID': v4().replace(/-/g, ''),
  //     },
  //     payload: JSON.stringify({
  //       course_id:'ca3265b045e84774b8d845a4c3c5b0a3',
  //       lesson_id:"fddec7afa702475ba080a2bc66643ccf",
  //       input:'',
  //       input_type:'start',
  //       preview_mode:'false',
  //     }),
  //   },
  // );

  // mock end
  source.onmessage = event => {
    try {
      const response = JSON.parse(event.data);
      console.log('======sse response======', response)
      if (onMessage) {
        onMessage(response);
      }
    } catch (e) {
      console.log(e);
    }
  };

  source.onerror = () => {};
  source.onclose = () => {};
  source.onopen = () => {};
  source.close = () => {};
  source.stream();

  return source;
};

/**
 * 获取课程学习记录
 * @param {*} lessonId
 *  shifu_bid : shifu_bid
    outline_bid: 大纲bid
    preview_mode: 是否为预览模式，可选值：　cook|preview|nomal ，为空时为normal
 * @returns
 */
export const getLessonStudyRecord = async ({
  shifu_bid,
  outline_bid,
  preview_mode,
}: GetLessonStudyRecordParams): Promise<LessonStudyRecords> => {
  return request.get(
    `/api/learn/shifu/${shifu_bid}/records/${outline_bid}?preview_mode=${preview_mode}`,
  ).catch(error => {
    // when error, return empty records, go run api
    return {
      records: [],
    };
  });

  // return {
  //   mdflow: 'string',
  //   records: [
  //     {
  //       block_type: 'content',
  //       content:
  //         '嘿你好，我是快刀青衣，AI学习圈的联合创始人。今天想和你聊聊我们刚上线的Get笔记新功能，绝对能帮你省不少事儿。对了，你现在主要做什么工作的？',
  //       generated_block_bid: '1',
  //       like_status: 'dislike',
  //     },
  //     {
  //       block_type: 'interaction',
  //       content:
  //         '?[支付按钮//'+SYS_INTERACTION_TYPE.LOGIN+']',
  //       generated_block_bid: '2',
  //       // like_status: 'like',
  //     },
  //   ],
  // };
};

/**
 * 点赞/点踩 生成内容
 * shifu_bid: shifu_bid
 * generated_block_bid: 生成内容bid
 * action: 动作 like|dislike|none
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
