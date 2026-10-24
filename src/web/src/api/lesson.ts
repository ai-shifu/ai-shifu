import request from '@/lib/request';
import { useSystemStore } from '@/store/useSystemStore';
import { useEnvStore } from '@/store/envStore';
import { useUserStore } from '@/store/useUserStore';
import { createRequestId, TRACE_REQUEST_ID_HEADER } from '@/lib/request-trace';

// A reset whose response was lost keeps its request id until a response arrives, so the
// retry is recognised by the backend receipt instead of clearing what the learner has
// started since, or spending a second use.
const pendingResetRequestIds = new Map<string, string>();

export const getLessonResetStatus = async (
  lessonId: string,
): Promise<{ can_reset: boolean }> => {
  const { courseId } = useEnvStore.getState();
  const { previewMode } = useSystemStore.getState();
  return request.get(
    `/api/learn/shifu/${courseId}/records/${lessonId}/reset-status?preview_mode=${previewMode}`,
    { skipErrorToast: true },
  );
};

export const getLessonTree = async (courseId: string, previewMode: boolean) => {
  return request.get(
    `/api/learn/shifu/${courseId}/outline?preview_mode=${previewMode}`,
  );
};

export const getScriptInfo = async (courseId: string, scriptId: string) => {
  return request.get(
    `/api/learn/shifu/${courseId}/outline/${scriptId}/preview_info`,
  );
};

export const resetChapter = async ({ lessonId: outline_bid }) => {
  const { courseId: shifu_bid } = useEnvStore.getState();
  const { previewMode } = useSystemStore.getState();
  const user = useUserStore.getState();
  const identity = user.userInfo?.user_id || user.getToken();
  const scope = JSON.stringify([identity, shifu_bid, outline_bid, previewMode]);
  const requestId = pendingResetRequestIds.get(scope) || createRequestId();
  pendingResetRequestIds.set(scope, requestId);
  const result = await request.delete(
    `/api/learn/shifu/${shifu_bid}/records/${outline_bid}?preview_mode=${previewMode}`,
    { headers: { [TRACE_REQUEST_ID_HEADER]: requestId }, skipErrorToast: true },
  );
  if (pendingResetRequestIds.get(scope) === requestId) {
    pendingResetRequestIds.delete(scope);
  }
  return result;
};
