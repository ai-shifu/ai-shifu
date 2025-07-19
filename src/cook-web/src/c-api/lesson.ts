import request from "@/lib/request";
import { useSystemStore } from '@/c-store/useSystemStore';

export const getLessonTree = async (courseId: string, previewMode: boolean) => {
  if (courseId === "" || courseId === null || courseId === undefined ) {
    return request.get(`/api/study/get_lesson_tree`);
  }
  return request.get(`/api/study/get_lesson_tree?course_id=${courseId}&preview_mode=${previewMode}`);
};

export const getScriptInfo = async (scriptId: string) => {
  const preview_mode = useSystemStore.getState().previewMode;
  return request.get(`/api/study/query-script-into?script_id=${scriptId}&preview_mode=${preview_mode}`);
};

export const resetChapter = async ({ chapterId }) => {
  const preview_mode = useSystemStore.getState().previewMode;
  return request.post('/api/study/reset-study-progress', { lesson_id: chapterId, preview_mode: preview_mode });
};
