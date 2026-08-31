import type { LearningMode } from './learningModeOptions';
import {
  readLocalStorageItem,
  writeLocalStorageItem,
} from '@/c-utils/runtimeStorage';

const LEARNING_MODE_STORAGE_PREFIX = 'course_learning_mode';

const buildLearningModeStorageKey = (courseId?: string) =>
  courseId ? `${LEARNING_MODE_STORAGE_PREFIX}:${courseId}` : '';

const isStoredLearningMode = (value: string | null): value is LearningMode =>
  value === 'listen' || value === 'read' || value === 'classroom';

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

  const value = readLocalStorageItem(
    key,
    '[learning-mode-storage] failed to read localStorage',
  );
  return isStoredLearningMode(value) ? value : null;
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

  writeLocalStorageItem(
    key,
    mode,
    '[learning-mode-storage] failed to write localStorage',
  );
};
