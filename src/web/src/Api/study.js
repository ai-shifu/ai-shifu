import { SSE } from "sse.js";
import Cookies from "js-cookie";
import request from "../Service/Request";
import { tokenStore } from "Service/storeUtil.js";

export const runScript = (course_id, lesson_id, input, input_type, script_id, onMessage) => {
  const source = new SSE(`${process.env.REACT_APP_BASEURL || ''}/api/study/run?token=${tokenStore.get()}`, {
  // const source = new SSE(`{''}/api/study/run?token=${tokenStore.get()}`, {
    headers: { "Content-Type": "application/json" },
    payload: JSON.stringify({
      course_id, lesson_id, input, input_type, script_id,
    }),
  });
  source.onmessage = (event) => {
    try {
      var response = JSON.parse(event.data);
      if (onMessage) {
        onMessage(response);
      }
    } catch (e) {
      console.log("error", e);
    }
  };
  source.onerror = (event) => {
    console.log("连接错误");
    console.log(event);
    // this.searchBoll = true;
  };
  source.onclose = (event) => {
    console.log("会话完成断开连接");
    // this.searchBoll = true;
    console.log(event);
  };
  source.onopen = (event) => {
    console.log("连接成功");
  };
  source.close = () => {
    console.log("主动断开连接");
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
    url: "/api/study/get_lesson_study_record?lesson_id=" + lessonId,
    method: "get",
  });
}
