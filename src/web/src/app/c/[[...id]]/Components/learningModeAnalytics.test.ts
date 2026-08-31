import {
  buildLastLearningModeAnalytics,
  buildLearningModeSelectionAnalytics,
  LAST_LEARNING_MODE_EVENT,
  shouldTrackLastLearningMode,
} from './learningModeAnalytics';

describe('learningModeAnalytics', () => {
  test('builds the accepted selection payload from bounded enums', () => {
    const payload = buildLearningModeSelectionAnalytics({
      from: 'read',
      to: 'listen',
      source: 'mobile_switch',
    });

    expect(payload).toEqual({
      from_learning_mode: 'read',
      to_learning_mode: 'listen',
      source: 'mobile_switch',
    });
    expect(payload).not.toHaveProperty('course_name');
    expect(payload).not.toHaveProperty('title');
    expect(payload).not.toHaveProperty('url');
  });

  test('keeps restored learner mode out of teacher preview', () => {
    expect(
      shouldTrackLastLearningMode({
        previewMode: true,
        storedLearningMode: 'listen',
        resolvedLearningMode: 'listen',
      }),
    ).toBe(false);
    expect(
      shouldTrackLastLearningMode({
        previewMode: false,
        storedLearningMode: null,
        resolvedLearningMode: 'read',
      }),
    ).toBe(false);
    expect(
      shouldTrackLastLearningMode({
        previewMode: false,
        storedLearningMode: 'listen',
        resolvedLearningMode: 'listen',
      }),
    ).toBe(true);
  });

  test('excludes stored modes that resolve to an available fallback', () => {
    expect(
      shouldTrackLastLearningMode({
        previewMode: false,
        storedLearningMode: 'listen',
        resolvedLearningMode: 'read',
      }),
    ).toBe(false);
    expect(
      shouldTrackLastLearningMode({
        previewMode: false,
        storedLearningMode: 'classroom',
        resolvedLearningMode: 'read',
      }),
    ).toBe(false);
  });

  test('builds the restored-mode payload from stable IDs and an enum', () => {
    expect(LAST_LEARNING_MODE_EVENT).toBe('learner_last_learning_mode');
    expect(
      buildLastLearningModeAnalytics({
        shifuBid: 'course-1',
        outlineBid: 'lesson-1',
        learningMode: 'classroom',
      }),
    ).toEqual({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      learning_mode: 'classroom',
    });
    expect(
      buildLastLearningModeAnalytics({
        shifuBid: 'course-1',
        outlineBid: '',
        learningMode: 'read',
      }),
    ).toEqual({
      shifu_bid: 'course-1',
      learning_mode: 'read',
    });
  });
});
