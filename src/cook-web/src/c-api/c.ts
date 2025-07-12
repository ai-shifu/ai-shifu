import { SSE } from 'sse.js';
import request from '@/lib/request';
import { v4 as uuid4 } from "uuid";
import { getStringEnv } from '@/c-utils/envUtils';
const token = getStringEnv('token');
const url = (getStringEnv('baseURL') || "") + "/api/study/run";

export const RunScript = (course_id, lesson_id, input, input_type, onMessage) => {

  const request_id = uuid4();
  const source = new SSE(url + "?token=" + token, {
    headers: { "Content-Type": "application/json", "X-Request-ID": request_id },
    payload: JSON.stringify({
        course_id,lesson_id,input,input_type
    }),
  });

  source.onmessage = (event) => {
    try {
      const response = JSON.parse(event.data);
      if (onMessage) {
        onMessage(response);
      }
    } catch (e) {
      console.log(e)
    }
  };
  source.onerror = () => {};
  source.onclose = () => {};
  source.onopen = () => {};
  source.close = () => {};
  source.stream();
  
  return source;
};

export const getLessonStudyRecord = async (lesson_id) => {
  return request.get("/api/study/get_lesson_study_record?lesson_id="+ lesson_id);
};
