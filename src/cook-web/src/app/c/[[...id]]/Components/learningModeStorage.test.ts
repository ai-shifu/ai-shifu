import {
  readLearningModeFromStorage,
  writeLearningModeToStorage,
} from './learningModeStorage';

describe('learningModeStorage', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('stores read and listen preferences per course', () => {
    writeLearningModeToStorage('course-1', 'listen');
    writeLearningModeToStorage('course-2', 'read');

    expect(readLearningModeFromStorage('course-1')).toBe('listen');
    expect(readLearningModeFromStorage('course-2')).toBe('read');
  });

  it('does not persist classroom mode as the learner default', () => {
    writeLearningModeToStorage('course-1', 'read');
    writeLearningModeToStorage('course-1', 'classroom');

    expect(readLearningModeFromStorage('course-1')).toBe('read');
  });

  it('ignores legacy or invalid stored values', () => {
    window.localStorage.setItem('course_learning_mode:course-1', 'classroom');

    expect(readLearningModeFromStorage('course-1')).toBeNull();
  });
});
