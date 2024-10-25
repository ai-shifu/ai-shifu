import request from "../Service/Request";

export const getCourseInfo = async (courseId) => {
  return request({
    url: `/api/course/get-course-info?course_id=${courseId}`,
  });
};
