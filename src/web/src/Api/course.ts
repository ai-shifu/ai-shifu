import request from "../Service/Request";

export const getCourseInfo = async (courseId: string, previewMode: boolean) => {
  if (courseId === "" || courseId === null || courseId === undefined ) {
    return request({
      url: `/api/course/get-course-info`,
    });
  }else{
  return request({
    url: `/api/course/get-course-info?course_id=${courseId}&preview_mode=${previewMode}`,
    });
  }
};
