import request from '@/lib/request';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useEnvStore } from '@/c-store/envStore';

export const getLessonTree = async (courseId: string, previewMode: boolean) => {
  return request.get(
    // `/api/study/get_lesson_tree?course_id=${courseId}&preview_mode=${previewMode}`,
    `/api/learn/shifu/${courseId}/outline-item-tree?preview_mode=${previewMode}`,
  );
};

export const getScriptInfo = async (scriptId: string) => {
  const preview_mode = useSystemStore.getState().previewMode;
  return request.get(
    `/api/study/query-script-into?script_id=${scriptId}&preview_mode=${preview_mode}`,
  );
};

export const resetChapter = async ({  chapterId: outline_bid }) => {
  const {courseId: shifu_bid} = useEnvStore.getState();
  return request.delete(`/api/learn/shifu/${shifu_bid}/records/${outline_bid}`);
};
