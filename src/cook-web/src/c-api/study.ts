import { SSE } from 'sse.js';
import request from "@/lib/request";
import { tokenStore } from '@/c-service/storeUtil';
import { v4 } from "uuid";
import { getStringEnv } from '@/c-utils/envUtils';
import { useSystemStore } from '@/c-store/useSystemStore';


export const runScript = (course_id, lesson_id, input, input_type, script_id, onMessage) => {
  let baseURL  = getStringEnv('baseURL');
  if (baseURL === "" || baseURL === "/") {
    baseURL = window.location.origin;
  }
  const preview_mode = useSystemStore.getState().previewMode;
  const source = new SSE(`${baseURL}/api/study/run?preview_mode=${preview_mode}&token=${tokenStore.get()}`, {
    headers: { "Content-Type": "application/json", "X-Request-ID": v4().replace(/-/g, '') },
    payload: JSON.stringify({
      course_id, lesson_id, input, input_type, script_id, preview_mode,
    }),
  });
  source.onmessage = (event) => {
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
 * @returns
 */
export const getLessonStudyRecord = async (lessonId) => {
  return request.get("/api/study/get_lesson_study_record?lesson_id=" + lessonId + "&preview_mode=" + useSystemStore.getState().previewMode);
};


export const scriptContentOperation = async (logID, interactionType ) => {
  return request.post('/api/study/script-content-operation', {
    log_id: logID,
    interaction_type: interactionType
  });
};
