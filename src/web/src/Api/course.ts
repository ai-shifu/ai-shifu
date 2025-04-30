import request from '../Service/Request';

export const getCourseInfo = async (courseId) => {
  if (courseId === '' || courseId === null || courseId === undefined) {
    return request({
      url: `/api/course/get-course-info`,
    });
  } else {
    return request({
      url: `/api/course/get-course-info?course_id=${courseId}`,
    });
  }
};
