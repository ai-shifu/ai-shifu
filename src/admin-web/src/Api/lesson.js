import request from "../Service/Request";

export const getLessonTree = async () => {
  return request({
    url: "/api/study/get_lesson_tree?course_id=dfca19aab2654fe4882e002a58567240",
    method: "get",
  });
}
