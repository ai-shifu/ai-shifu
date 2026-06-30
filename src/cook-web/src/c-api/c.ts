import { SSE } from 'sse.js';
import request from '@/lib/request';
import { getResolvedBaseURL, getStringEnv } from '@/c-utils/envUtils';
import { buildTraceHeaders } from '@/lib/request-trace';

export const RunScript = (
  course_id,
  lesson_id,
  input,
  input_type,
  onMessage,
) => {
  const token = getStringEnv('token');
  const url = `${getResolvedBaseURL()}/api/study/run`;
  const traceHeaders = buildTraceHeaders({
    'Content-Type': 'application/json',
  });
  const source = new SSE(url + '?token=' + token, {
    headers: traceHeaders.headers,
    payload: JSON.stringify({
      course_id,
      lesson_id,
      input,
      input_type,
    }),
  });

  source.onmessage = event => {
    try {
      const response = JSON.parse(event.data);
      if (onMessage) {
        onMessage(response);
      }
    } catch {
      // ignore malformed SSE payloads
    }
  };
  source.onerror = () => {};
  source.onclose = () => {};
  source.onopen = () => {};
  source.close = () => {};
  source.stream();

  return source;
};

export const getLessonStudyRecord = async lesson_id => {
  return request.get(
    '/api/study/get_lesson_study_record?lesson_id=' + lesson_id,
  );
};
