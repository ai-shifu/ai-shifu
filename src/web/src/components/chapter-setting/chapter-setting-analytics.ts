import type { LearningPermission } from '@/api/learning';

type BaseOutlineSaveAnalyticsInput = {
  outlineBid: string;
  shifuBid?: string;
  saveType: 'auto' | 'manual';
};

type LessonSettingSaveAnalyticsInput = BaseOutlineSaveAnalyticsInput & {
  learningPermission: LearningPermission;
  hideChapter: boolean;
};

export const buildLessonSettingSaveAnalytics = ({
  outlineBid,
  shifuBid,
  saveType,
  learningPermission,
  hideChapter,
}: LessonSettingSaveAnalyticsInput) => ({
  outline_bid: outlineBid,
  shifu_bid: shifuBid || '',
  save_type: saveType,
  variant: 'lesson',
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
