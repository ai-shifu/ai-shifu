import request from '../Service/Request';
export const getLessonTree = async (courseId) => {
  if (courseId === '' || courseId === null || courseId === undefined) {
    return request({
      url: `/api/study/get_lesson_tree`,
    });
  }
  return request({
    url: `/api/study/get_lesson_tree?course_id=${courseId}`,
    method: 'GET',
  });
};

export const getScriptInfo = async (scriptId) => {
  return request({
    url: `/api/study/query-script-into?script_id=${scriptId}`,
    method: 'GET',
  });
};

export const resetChapter = async ({ chapterId }) => {
  return request({
    url: '/api/study/reset-study-progress',
    method: 'POST',
    data: { lesson_id: chapterId },
  });
};
