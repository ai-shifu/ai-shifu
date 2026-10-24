import type { LearningPermission } from '@/api/studyV2';

type BaseOutlineSaveAnalyticsInput = {
  outlineBid: string;
  shifuBid?: string;
  saveType: 'auto' | 'manual';
  promptChange: 'unchanged' | 'updated' | 'cleared';
};

type LessonSettingSaveAnalyticsInput = BaseOutlineSaveAnalyticsInput & {
  variant: 'chapter' | 'lesson';
  learningPermission: LearningPermission;
  hideChapter: boolean;
};

export const buildLessonSettingSaveAnalytics = ({
  outlineBid,
  shifuBid,
  saveType,
  promptChange,
  variant,
  learningPermission,
  hideChapter,
}: LessonSettingSaveAnalyticsInput) => ({
  outline_bid: outlineBid,
  shifu_bid: shifuBid || '',
  save_type: saveType,
  prompt_change: promptChange,
  variant,
  learning_permission: learningPermission,
  hide_chapter: hideChapter,
});

export const buildOutlinePromptSaveAnalytics = ({
  outlineBid,
  shifuBid,
  saveType,
  promptChange,
}: BaseOutlineSaveAnalyticsInput) => ({
  outline_bid: outlineBid,
  shifu_bid: shifuBid || '',
  save_type: saveType,
  prompt_change: promptChange,
});
