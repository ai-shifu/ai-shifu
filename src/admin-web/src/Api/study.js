import { SSE } from "sse.js";
import Cookies from "js-cookie";
import store from "store";
import request from "../Service/Request";

const url = (process.env.REACT_APP_BASEURL || "") + "/api/study/run";

export const RunScript = (course_id,lesson_id,input,input_type,onMessage) => {

  var source = new SSE(url + "?token=" + store.get("token"), {
    headers: { "Content-Type": "application/json" },
    payload: JSON.stringify({
        course_id,lesson_id,input,input_type
    }),
  });
  source.onmessage = (event) => {
    try {
      // var response = eval('('+event.data+")")
      var response = JSON.parse(event.data);
      // console.log("response", response);
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
    console.log(event);
  };
  source.close = () => {
    console.log("主动断开连接");
  };
  source.stream();
  return source;
};





export const getLessonStudyRecord = async (lesson_id) => {
  return request({
    url: "/api/study/get_lesson_study_record?lesson_id="+ lesson_id,
    method: "get",
  });
}
