import request from '@/lib/request';

export type RetakePolicy = {
  available: boolean;
  configured: boolean;
  limit: number | null;
};
export type RetakeStatus = {
  available: boolean;
  limit: number | null;
  used: number;
  reserved: number;
  remaining: number | null;
  allowed: boolean;
  in_progress: boolean;
};
export const getRetakePolicy = async (
  courseId: string,
): Promise<RetakePolicy> =>
  (
    await request.get(`/api/learn/shifu/${courseId}/retake-policy`, {
      skipErrorToast: true,
    })
  ).data;
export const setRetakePolicy = async (
  courseId: string,
  limit: number | null,
): Promise<RetakePolicy> =>
  (await request.put(`/api/learn/shifu/${courseId}/retake-policy`, { limit }))
    .data;
export const getRetakeStatus = async (
  courseId: string,
  lessonId: string,
): Promise<RetakeStatus> =>
  (
    await request.get(
      `/api/learn/shifu/${courseId}/retake-status/${lessonId}`,
      { skipErrorToast: true },
    )
  ).data;
