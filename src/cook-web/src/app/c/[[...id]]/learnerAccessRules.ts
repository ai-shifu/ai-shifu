import type { LearningPermission } from '@/c-api/studyV2';

const TRIAL_PERMISSION: LearningPermission = 'trial';
const NORMAL_PERMISSION: LearningPermission = 'normal';

export type LearnerLessonAccessAction =
  | { type: 'allow' }
  | { type: 'login'; redirectUrl: string }
  | {
      type: 'pay';
      modalType: LearningPermission | string;
      payload: { chapterId: string; lessonId: string };
    };

export type LearnerLessonAccessInput = {
  type?: LearningPermission | string;
  isPaid?: boolean;
  isLoggedIn: boolean;
  previewMode: boolean;
  chapterId: string;
  lessonId: string;
  currentPathAndSearch: string;
};

export const buildLearnerLoginRedirectUrl = (currentPathAndSearch: string) =>
  `/login?redirect=${encodeURIComponent(currentPathAndSearch)}`;

export const resolveLearnerLessonAccess = ({
  type,
  isPaid,
  isLoggedIn,
  previewMode,
  chapterId,
  lessonId,
  currentPathAndSearch,
}: LearnerLessonAccessInput): LearnerLessonAccessAction => {
  const needsLogin =
    (type === TRIAL_PERMISSION || type === NORMAL_PERMISSION) && !isLoggedIn;

  if (!previewMode && needsLogin) {
    return {
      type: 'login',
      redirectUrl: buildLearnerLoginRedirectUrl(currentPathAndSearch),
    };
  }

  if (!previewMode && type === NORMAL_PERMISSION && !isPaid) {
    return {
      type: 'pay',
      modalType: type,
      payload: {
        chapterId,
        lessonId,
      },
    };
  }

  return { type: 'allow' };
};
