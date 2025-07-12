import request from "@/lib/request";

export const getCourseInfo = async (courseId: string, previewMode: boolean) => {
  if (courseId === "" || courseId === null || courseId === undefined ) {
    return request.get(`/api/course/get-course-info`);
  }else{
    return request.get(`/api/course/get-course-info?course_id=${courseId}&preview_mode=${previewMode}`);
  }
};
