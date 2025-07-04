import { SSE } from 'sse.js';
import request from "../Service/Request";
import { tokenStore } from 'Service/storeUtil';
import { v4 } from "uuid";
import { getStringEnv } from 'Utils/envUtils';
import { useSystemStore } from '../stores/useSystemStore';


export const runScript = (course_id, lesson_id, input, input_type, script_id, onMessage, reload_script_id = null) => {
  let baseURL  = getStringEnv('baseURL');
  if (baseURL === "" || baseURL === "/") {
    baseURL = window.location.origin;
  }
  const preview_mode = useSystemStore.getState().previewMode;

  const payload = {
    course_id, lesson_id, input, input_type, script_id, preview_mode,
  };

  // 如果传入了 reload_script_id，添加到请求体中
  if (reload_script_id) {
    payload.reload_script_id = reload_script_id;
  }

  const source = new SSE(`${baseURL}/api/study/run?preview_mode=${preview_mode}&token=${tokenStore.get()}`, {
    headers: { "Content-Type": "application/json", "X-Request-ID": v4().replace(/-/g, '') },
    payload: JSON.stringify(payload),
  });
  source.onmessage = (event) => {
    try {
      var response = JSON.parse(event.data);
      if (onMessage) {
        onMessage(response);
      }
    } catch (e) {
    }
  };
  source.onerror = (event) => {
  };
  source.onclose = (event) => {
  };
  source.onopen = (event) => {
  };
  source.close = () => {
  };
  source.stream();
  return source;
};




/**
 * 获取课程学习记录
 * @param {*} lessonId
 * @returns
 */
export const getLessonStudyRecord = async (lessonId) => {
  return request({
    url: "/api/study/get_lesson_study_record?lesson_id=" + lessonId + "&preview_mode=" + useSystemStore.getState().previewMode,
    method: "get",
  });
};


export const scriptContentOperation = async (logID, interactionType ) => {
  return request({
    url: '/api/study/script-content-operation',
    method: 'POST',
    data: {
      log_id: logID,
      interaction_type: interactionType
    }
  });
};
