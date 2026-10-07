import request from '@/lib/request';

export type CourseMemoryEntry = {
  value_id: string;
  key: string;
  value: string;
  updated_at: string | null;
};

export type CourseMemoryPage = {
  items: CourseMemoryEntry[];
  next_before: string | null;
};

export const listCourseMemory = (
  courseId: string,
  before?: string,
): Promise<CourseMemoryPage> =>
  request.get('/api/user/course-memory', {
    params: { course_id: courseId, ...(before ? { before } : {}) },
    skipErrorToast: true,
  });

export const deleteCourseMemory = (
  courseId: string,
  valueBid: string,
): Promise<{ conflict: boolean }> =>
  request.post(
    '/api/user/course-memory',
    { course_id: courseId, value_id: valueBid },
    { skipErrorToast: true },
  );
