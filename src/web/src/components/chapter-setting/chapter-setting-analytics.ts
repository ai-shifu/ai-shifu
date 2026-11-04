import type { LearningPermission } from '@/api/learning';

type BaseOutlineSaveAnalyticsInput = {
  outlineBid: string;
  shifuBid?: string;
  saveType: 'auto' | 'manual';
};

type LessonSettingSaveAnalyticsInput = BaseOutlineSaveAnalyticsInput & {
  variant: 'lesson';
  learningPermission: LearningPermission;
  hideChapter: boolean;
};

export const buildLessonSettingSaveAnalytics = ({
  outlineBid,
  shifuBid,
  saveType,
  variant,
  learningPermission,
  hideChapter,
}: LessonSettingSaveAnalyticsInput) => ({
  outline_bid: outlineBid,
  shifu_bid: shifuBid || '',
  save_type: saveType,
  variant,
  learning_permission: learningPermission,
  hide_chapter: hideChapter,
});

export const buildChapterSettingSaveAnalytics = ({
  outlineBid,
  shifuBid,
  saveType,
}: BaseOutlineSaveAnalyticsInput) => ({
  outline_bid: outlineBid,
  shifu_bid: shifuBid || '',
  save_type: saveType,
});
