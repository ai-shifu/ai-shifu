import request from "../Service/Request";
import { useSystemStore } from '../stores/useSystemStore';

export const getLessonTree = async (courseId: string, previewMode: boolean) => {
  if (courseId === "" || courseId === null || courseId === undefined ) {
    return request({
      url: `/api/study/get_lesson_tree`,
    });
  }
  return request({
    url: `/api/study/get_lesson_tree?course_id=${courseId}&preview_mode=${previewMode}`,
    method: "GET",
  });
};

export const getScriptInfo = async (scriptId) => {
  const preview_mode = useSystemStore.getState().previewMode;
  return request({
    url: `/api/study/query-script-into?script_id=${scriptId}&preview_mode=${preview_mode}`,
    method: 'GET',

  });
};

export const resetChapter = async ({ chapterId }) => {
  const preview_mode = useSystemStore.getState().previewMode;
  return request({
    url: '/api/study/reset-study-progress',
    method: 'POST',
    data: { lesson_id: chapterId, preview_mode: preview_mode }
  });
};
