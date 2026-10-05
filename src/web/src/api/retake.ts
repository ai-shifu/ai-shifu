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
export const getRetakePolicy = (courseId: string): Promise<RetakePolicy> =>
  request.get(`/api/learn/shifu/${courseId}/retake-policy`, {
    skipErrorToast: true,
  });
export const setRetakePolicy = (
  courseId: string,
  limit: number | null,
): Promise<RetakePolicy> =>
  request.put(`/api/learn/shifu/${courseId}/retake-policy`, { limit });
export const getRetakeStatus = (
  courseId: string,
  lessonId: string,
): Promise<RetakeStatus> =>
  request.get(`/api/learn/shifu/${courseId}/retake-status/${lessonId}`, {
    skipErrorToast: true,
  });
