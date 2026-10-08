import request from '@/lib/request';

export type RetakeStatus = {
  available: boolean;
  quota_exempt?: boolean;
  limit?: number | null;
  used?: number;
  reserved?: number;
  remaining?: number | null;
  allowed: boolean;
  in_progress: boolean;
};
export const getRetakeStatus = (
  courseId: string,
  lessonId: string,
): Promise<RetakeStatus> =>
  request.get(`/api/learn/shifu/${courseId}/retake-status/${lessonId}`, {
    skipErrorToast: true,
  });
