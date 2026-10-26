import {
  readLearningModeFromStorage,
  writeLearningModeToStorage,
} from './learningModeStorage';

describe('learningModeStorage', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('stores read, listen, and classroom preferences per course', () => {
    writeLearningModeToStorage('course-1', 'listen');
    writeLearningModeToStorage('course-2', 'read');
    writeLearningModeToStorage('course-3', 'classroom');

    expect(readLearningModeFromStorage('course-1')).toBe('listen');
    expect(readLearningModeFromStorage('course-2')).toBe('read');
    expect(readLearningModeFromStorage('course-3')).toBe('classroom');
  });

  it('ignores legacy or invalid stored values', () => {
    window.localStorage.setItem('course_learning_mode:course-1', 'present');

    expect(readLearningModeFromStorage('course-1')).toBeNull();
  });
});
