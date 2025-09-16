import { SSE } from 'sse.js';
import request from '@/lib/request';
import { tokenStore } from '@/c-service/storeUtil';
import { v4 } from 'uuid';
import { getStringEnv } from '@/c-utils/envUtils';
import { useSystemStore } from '@/c-store/useSystemStore';

// ===== Types for Learn/Shifu records mock =====
export type BlockType = 'content' | 'interaction';
export type LikeStatus = 'like' | 'dislike' | 'none';

export interface StudyRecordItem {
  block_type: BlockType;
  content: string;
  generated_block_bid: string;
  like_status?: LikeStatus;
}

export interface LessonStudyRecords {
  mdflow: string;
  records: StudyRecordItem[];
}

export interface GetLessonStudyRecordParams {
  shifu_bid: string;
  outline_bid: string;
  // Optional preview mode flag
  preview_mode?: 'cook' | 'preview' | 'normal';
}

export const runScript = (
  course_id,
  lesson_id,
  input,
  input_type,
  script_id,
  onMessage,
) => {
  let baseURL = getStringEnv('baseURL');
  if (baseURL === '' || baseURL === '/') {
    baseURL = window.location.origin;
  }
  const preview_mode = useSystemStore.getState().previewMode;
  const source = new SSE(
    `${baseURL}/api/study/run?preview_mode=${preview_mode}&token=${tokenStore.get()}`,
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': v4().replace(/-/g, ''),
      },
      payload: JSON.stringify({
        course_id,
        lesson_id,
        input,
        input_type,
        script_id,
        preview_mode,
      }),
    },
  );
  source.onmessage = event => {
    try {
      const response = JSON.parse(event.data);
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
  // return request.get(
  //   `/api/learn/shifu/${shifu_bid}/records/${outline_bid}?preview_mode=${preview_mode}`,
  // );

  return {
    mdflow: 'string',
    records: [
      {
        block_type: 'content',
        content:
          '嘿你好，我是快刀青衣，AI学习圈的联合创始人。今天想和你聊聊我们刚上线的Get笔记新功能，绝对能帮你省不少事儿。对了，你现在主要做什么工作的？',
        generated_block_bid: '1',
        like_status: 'dislike',
      },
      {
        block_type: 'interaction',
        content:
          '?[%{{背景}}创业者|大学生|自媒体|...请告诉我您的身份信息]',
        generated_block_bid: '2',
        // like_status: 'like',
      },
    ],
  };
};

export const scriptContentOperation = async (logID, interactionType) => {
  return request.post('/api/study/script-content-operation', {
    log_id: logID,
    interaction_type: interactionType,
  });
};
