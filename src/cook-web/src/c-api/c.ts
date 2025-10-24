import request from '@/lib/request';
import { v4 as uuid4 } from 'uuid';
import { getStringEnv } from '@/c-utils/envUtils';
import { createFetchSseSource } from './sseClient';
const token = getStringEnv('token');
const url = (getStringEnv('baseURL') || '') + '/api/study/run';

export const RunScript = (
  course_id,
  lesson_id,
  input,
  input_type,
  onMessage,
) => {
  const request_id = uuid4();
  const source = createFetchSseSource({
    url: `${url}?token=${token}`,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': request_id,
    },
    body: JSON.stringify({
      course_id,
      lesson_id,
      input,
      input_type,
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

export const getLessonStudyRecord = async lesson_id => {
  return request.get(
    '/api/study/get_lesson_study_record?lesson_id=' + lesson_id,
  );
};
