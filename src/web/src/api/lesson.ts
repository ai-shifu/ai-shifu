import { useUserStore } from '@/store';
import {
  finishRetakeRequest,
  retakeRequestIdentity,
} from '@/lib/retakeRequestIdentity';
import request from '@/lib/request';
import { useSystemStore } from '@/store/useSystemStore';
import { useEnvStore } from '@/store/envStore';

export const getLessonTree = async (courseId: string, previewMode: boolean) => {
  return request.get(
    // `/api/study/get_lesson_tree?course_id=${courseId}&preview_mode=${previewMode}`,
    `/api/learn/shifu/${courseId}/outline-item-tree?preview_mode=${previewMode}`,
  );
};

export const getScriptInfo = async (courseId: string, scriptId: string) => {
  const preview_mode = useSystemStore.getState().previewMode;
  return request.get(
    `/api/learn/shifu/${courseId}/generated-contents/${scriptId}?preview_mode=${preview_mode}`,
  );
};

export const resetChapter = async ({ lessonId: outline_bid }) => {
  const { courseId: shifu_bid } = useEnvStore.getState();
  const preview = useSystemStore.getState().previewMode;
  const user = useUserStore.getState().userInfo?.user_id || '';
  const scope = `${user}:${shifu_bid}:${outline_bid}:${preview}`;
  const requestId = retakeRequestIdentity(scope);
  try {
    const response = await request.delete(
      `/api/learn/shifu/${shifu_bid}/records/${outline_bid}?preview_mode=${preview}`,
      {
        headers: { 'X-Retake-Request-Id': requestId },
      },
    );
    finishRetakeRequest(scope);
    return response;
  } catch (error) {
    // A released attempt needs a fresh identity. Unknown transport outcomes
    // retain the identity so retry cannot reset/charge twice.
    if ((error as { code?: number }).code === 4032) finishRetakeRequest(scope);
    throw error;
  }
};
