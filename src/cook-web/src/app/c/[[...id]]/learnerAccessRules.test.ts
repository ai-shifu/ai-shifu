import {
  buildLearnerLoginRedirectUrl,
  resolveLearnerLessonAccess,
} from './learnerAccessRules';

const LEARNING_PERMISSION = {
  NORMAL: 'normal',
  TRIAL: 'trial',
  GUEST: 'guest',
} as const;

const baseInput = {
  type: LEARNING_PERMISSION.NORMAL,
  isPaid: false,
  isLoggedIn: true,
  previewMode: false,
  chapterId: 'chapter-1',
  lessonId: 'lesson-1',
  currentPathAndSearch: '/c/course-1?lessonid=lesson-1',
};

describe('resolveLearnerLessonAccess', () => {
  it('sends guests to login for trial lessons outside preview mode', () => {
    expect(
      resolveLearnerLessonAccess({
        ...baseInput,
        type: LEARNING_PERMISSION.TRIAL,
        isLoggedIn: false,
        isPaid: true,
      }),
    ).toEqual({
      type: 'login',
      redirectUrl: '/login?redirect=%2Fc%2Fcourse-1%3Flessonid%3Dlesson-1',
    });
  });

  it('sends guests to login before payment for normal unpaid lessons', () => {
    expect(
      resolveLearnerLessonAccess({
        ...baseInput,
        type: LEARNING_PERMISSION.NORMAL,
        isLoggedIn: false,
        isPaid: false,
      }),
    ).toMatchObject({ type: 'login' });
  });

  it('opens payment for logged-in learners on normal unpaid lessons', () => {
    expect(resolveLearnerLessonAccess(baseInput)).toEqual({
      type: 'pay',
      modalType: LEARNING_PERMISSION.NORMAL,
      payload: {
        chapterId: 'chapter-1',
        lessonId: 'lesson-1',
      },
    });
  });

  it('allows guest lessons without login or payment', () => {
    expect(
      resolveLearnerLessonAccess({
        ...baseInput,
        type: LEARNING_PERMISSION.GUEST,
        isLoggedIn: false,
        isPaid: false,
      }),
    ).toEqual({ type: 'allow' });
  });

  it('allows every permission check in preview mode', () => {
    expect(
      resolveLearnerLessonAccess({
        ...baseInput,
        type: LEARNING_PERMISSION.NORMAL,
        isLoggedIn: false,
        isPaid: false,
        previewMode: true,
      }),
    ).toEqual({ type: 'allow' });
  });

  it('allows logged-in learners on paid normal lessons', () => {
    expect(
      resolveLearnerLessonAccess({
        ...baseInput,
        type: LEARNING_PERMISSION.NORMAL,
        isLoggedIn: true,
        isPaid: true,
      }),
    ).toEqual({ type: 'allow' });
  });
});

describe('buildLearnerLoginRedirectUrl', () => {
  it('keeps the current path and query in the redirect parameter', () => {
    expect(buildLearnerLoginRedirectUrl('/c/course-1?mode=listen')).toBe(
      '/login?redirect=%2Fc%2Fcourse-1%3Fmode%3Dlisten',
    );
  });
});
