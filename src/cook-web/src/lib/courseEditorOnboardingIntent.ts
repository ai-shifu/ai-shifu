export const COURSE_EDITOR_ONBOARDING_INTENT_KEY =
  'ai-shifu:course-editor-onboarding-intent';

const COURSE_EDITOR_ONBOARDING_INTENT_TTL_MS = 3 * 60 * 60 * 1000;
const LOBSTER_CREATE_SOURCE = 'lobster_create';

type CourseEditorOnboardingIntent = {
  source: typeof LOBSTER_CREATE_SOURCE;
  createdAt: number;
};

const getStorage = (): Storage | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
};

export const clearCourseEditorOnboardingIntent = () => {
  const storage = getStorage();
  if (!storage) {
    return;
  }
  storage.removeItem(COURSE_EDITOR_ONBOARDING_INTENT_KEY);
};

export const markLobsterCourseEditorOnboardingIntent = () => {
  const storage = getStorage();
  if (!storage) {
    return;
  }
  const intent: CourseEditorOnboardingIntent = {
    source: LOBSTER_CREATE_SOURCE,
    createdAt: Date.now(),
  };
  storage.setItem(COURSE_EDITOR_ONBOARDING_INTENT_KEY, JSON.stringify(intent));
};

export const getPendingCourseEditorOnboardingSource = (): string => {
  const storage = getStorage();
  if (!storage) {
    return '';
  }

  const rawIntent = storage.getItem(COURSE_EDITOR_ONBOARDING_INTENT_KEY);
  if (!rawIntent) {
    return '';
  }

  try {
    const intent = JSON.parse(rawIntent) as Partial<CourseEditorOnboardingIntent>;
    const isValidSource = intent.source === LOBSTER_CREATE_SOURCE;
    const createdAt =
      typeof intent.createdAt === 'number' && Number.isFinite(intent.createdAt)
        ? intent.createdAt
        : 0;
    const isExpired =
      createdAt <= 0 ||
      Date.now() - createdAt > COURSE_EDITOR_ONBOARDING_INTENT_TTL_MS;

    if (!isValidSource || isExpired) {
      clearCourseEditorOnboardingIntent();
      return '';
    }

    return LOBSTER_CREATE_SOURCE;
  } catch {
    clearCourseEditorOnboardingIntent();
    return '';
  }
};
