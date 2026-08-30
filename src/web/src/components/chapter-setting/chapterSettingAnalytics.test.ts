import {
  buildLessonSettingSaveAnalytics,
  buildOutlinePromptSaveAnalytics,
} from './chapterSettingAnalytics';

describe('chapter setting analytics', () => {
  it('keeps lesson settings to stable IDs and bounded state', () => {
    const payload = buildLessonSettingSaveAnalytics({
      outlineBid: 'lesson-1',
      shifuBid: 'course-1',
      saveType: 'manual',
      variant: 'lesson',
      learningPermission: 'trial',
      hideChapter: false,
    });

    expect(payload).toEqual({
      outline_bid: 'lesson-1',
      shifu_bid: 'course-1',
      save_type: 'manual',
      variant: 'lesson',
      learning_permission: 'trial',
      hide_chapter: false,
    });
    expect(payload).not.toHaveProperty('system_prompt');
    expect(payload).not.toHaveProperty('name');
    expect(payload).not.toHaveProperty('description');
  });

  it('never includes prompt content in prompt-save analytics', () => {
    expect(
      buildOutlinePromptSaveAnalytics({
        outlineBid: 'chapter-1',
        shifuBid: 'course-1',
        saveType: 'auto',
      }),
    ).toEqual({
      outline_bid: 'chapter-1',
      shifu_bid: 'course-1',
      save_type: 'auto',
    });
  });
});
