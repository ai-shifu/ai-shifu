import type { AdminOperationCourseUserItem } from '../operation-course-types';

export type CourseUserPaymentStatus = 'all' | 'paid' | 'unpaid';

export type CourseUserFilters = {
  keyword: string;
  userRole: string;
  learningStatus: string;
  paymentStatus: CourseUserPaymentStatus;
};

export const USER_COLUMN_MIN_WIDTH = 80;
export const USER_COLUMN_MAX_WIDTH = 320;
export const USER_COLUMN_WIDTH_STORAGE_KEY =
  'adminOperationCourseUserColumnWidths';
export const USER_COLUMN_DEFAULT_WIDTHS = {
  account: 170,
  nickname: 140,
  userRole: 120,
  learningProgress: 120,
  learningStatus: 120,
  isPaid: 90,
  totalPaidAmount: 120,
  lastLearnedAt: 170,
  lastLoginAt: 170,
  joinedAt: 170,
  action: 90,
} as const;

export type UserColumnKey = keyof typeof USER_COLUMN_DEFAULT_WIDTHS;
export const USER_COLUMN_KEYS = Object.keys(
  USER_COLUMN_DEFAULT_WIDTHS,
) as UserColumnKey[];

export const createCourseUserFilters = (): CourseUserFilters => ({
  keyword: '',
  userRole: 'all',
  learningStatus: 'all',
  paymentStatus: 'all',
});

export const getCourseUserLearningProgress = (
  courseUser: AdminOperationCourseUserItem,
) => ({
  learnedLessonCount: courseUser.learned_lesson_count,
  totalLessonCount: courseUser.total_lesson_count,
});
