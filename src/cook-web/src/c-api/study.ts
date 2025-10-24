import request from '@/lib/request';
import { tokenStore } from '@/c-service/storeUtil';
import { v4 } from 'uuid';
import { getStringEnv } from '@/c-utils/envUtils';
import { useSystemStore } from '@/c-store/useSystemStore';
import { createFetchSseSource } from './sseClient';

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
  const source = createFetchSseSource({
    url: `${baseURL}/api/study/run?preview_mode=${preview_mode}&token=${tokenStore.get()}`,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': v4().replace(/-/g, ''),
    },
    body: JSON.stringify({
      course_id,
      lesson_id,
      input,
      input_type,
      script_id,
      preview_mode,
    }),
    onOpen: () => {
      console.log('[SSE connection open]');
    },
    onClose: () => {
      console.log('[SSE connection close]');
    },
    onError: err => {
      if (err?.name === 'AbortError') {
        return;
      }
      console.error('[SSE error]', err);
    },
  });
  source.addEventListener('message', event => {
    try {
      const response = JSON.parse(event.data);
      if (onMessage) {
        onMessage(response);
      }
    } catch (e) {
      console.log(e);
    }
  });

  return source;
};

/**
 * Fetch course study records
 * @param {*} lessonId
 * @returns
 */
export const getLessonStudyRecord = async lessonId => {
  return request.get(
    '/api/study/get_lesson_study_record?lesson_id=' +
      lessonId +
      '&preview_mode=' +
      useSystemStore.getState().previewMode,
  );
};

export const scriptContentOperation = async (logID, interactionType) => {
  return request.post('/api/study/script-content-operation', {
    log_id: logID,
    interaction_type: interactionType,
  });
};
