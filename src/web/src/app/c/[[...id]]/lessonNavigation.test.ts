import {
  applyLessonSelection,
  resolveRequestedLessonId,
} from './lessonNavigation';

describe('applyLessonSelection', () => {
  it('updates local lesson selection immediately in the same chapter', () => {
    const updateSelectedLesson = jest.fn();
    const updateLessonId = jest.fn();
    const updateChapterId = jest.fn();
    const syncLessonUrl = jest.fn();

    const result = applyLessonSelection({
      lessonId: 'lesson-2',
      currentChapterId: 'chapter-1',
      getChapterByLesson: () => ({ id: 'chapter-1' }),
      updateSelectedLesson,
      updateLessonId,
      updateChapterId,
      syncLessonUrl,
    });

    expect(result).toEqual({
      chapterId: 'chapter-1',
      lessonId: 'lesson-2',
    });
    expect(updateSelectedLesson).toHaveBeenCalledWith('lesson-2', false);
    expect(updateLessonId).toHaveBeenCalledWith('lesson-2');
    expect(syncLessonUrl).toHaveBeenCalledWith('lesson-2');
    expect(updateChapterId).not.toHaveBeenCalled();
  });

  it('syncs chapter state when the lesson belongs to another chapter', () => {
    const updateSelectedLesson = jest.fn();
    const updateLessonId = jest.fn();
    const updateChapterId = jest.fn();
    const syncLessonUrl = jest.fn();

    const result = applyLessonSelection({
      lessonId: 'lesson-3',
      currentChapterId: 'chapter-1',
      forceExpand: true,
      getChapterByLesson: () => ({ id: 'chapter-2' }),
      updateSelectedLesson,
      updateLessonId,
      updateChapterId,
      syncLessonUrl,
    });

    expect(result).toEqual({
      chapterId: 'chapter-2',
      lessonId: 'lesson-3',
    });
    expect(updateSelectedLesson).toHaveBeenCalledWith('lesson-3', true);
    expect(updateLessonId).toHaveBeenCalledWith('lesson-3');
    expect(syncLessonUrl).toHaveBeenCalledWith('lesson-3');
    expect(updateChapterId).toHaveBeenCalledWith('chapter-2');
  });

  it('does nothing when the lesson does not map to a chapter', () => {
    const updateSelectedLesson = jest.fn();
    const updateLessonId = jest.fn();
    const updateChapterId = jest.fn();
    const syncLessonUrl = jest.fn();

    const result = applyLessonSelection({
      lessonId: 'lesson-missing',
      currentChapterId: 'chapter-1',
      getChapterByLesson: () => null,
      updateSelectedLesson,
      updateLessonId,
      updateChapterId,
      syncLessonUrl,
    });

    expect(result).toBeNull();
    expect(updateSelectedLesson).not.toHaveBeenCalled();
    expect(updateLessonId).not.toHaveBeenCalled();
    expect(updateChapterId).not.toHaveBeenCalled();
    expect(syncLessonUrl).not.toHaveBeenCalled();
  });
});

describe('resolveRequestedLessonId', () => {
  it('prefers selected lesson over store and url values', () => {
    expect(
      resolveRequestedLessonId('lesson-selected', 'lesson-store', 'lesson-url'),
    ).toBe('lesson-selected');
  });

  it('falls back to url lesson before store lesson', () => {
    expect(resolveRequestedLessonId('', 'lesson-store', 'lesson-url')).toBe(
      'lesson-url',
    );
  });

  it('uses store lesson only when selected and url lessons are both empty', () => {
    expect(resolveRequestedLessonId('', 'lesson-store', '')).toBe(
      'lesson-store',
    );
  });
});
