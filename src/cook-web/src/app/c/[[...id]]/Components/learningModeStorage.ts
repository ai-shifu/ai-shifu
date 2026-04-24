import type { LearningMode } from './learningModeOptions';

const LEARNING_MODE_STORAGE_PREFIX = 'course_learning_mode';

const buildLearningModeStorageKey = (courseId?: string) =>
  courseId ? `${LEARNING_MODE_STORAGE_PREFIX}:${courseId}` : '';

const isLearningMode = (value: string | null): value is LearningMode =>
  value === 'listen' || value === 'read';

export const readLearningModeFromStorage = (
  courseId?: string,
): LearningMode | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  const key = buildLearningModeStorageKey(courseId);
  if (!key) {
    return null;
  }

  try {
    const value = window.localStorage.getItem(key);
    return isLearningMode(value) ? value : null;
  } catch (error) {
    console.warn('Failed to read learning mode from storage', error);
    return null;
  }
};

export const writeLearningModeToStorage = (
  courseId: string,
  mode: LearningMode,
) => {
  if (typeof window === 'undefined') {
    return;
  }

  const key = buildLearningModeStorageKey(courseId);
  if (!key) {
    return;
  }

  try {
    window.localStorage.setItem(key, mode);
  } catch (error) {
    console.warn('Failed to write learning mode to storage', error);
  }
};
