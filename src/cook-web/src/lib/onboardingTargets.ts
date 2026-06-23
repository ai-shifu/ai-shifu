export const ONBOARDING_TARGET_ATTR = 'data-onboarding-id';

export const ONBOARDING_TARGET_IDS = {
  billingBalance: 'billing-balance',
  billingUpgrade: 'billing-upgrade',
  billingCard: 'billing-card',
  guideCourseCard: 'guide-course-card',
  courseCreationEntry: 'course-creation-entry',
  blankCreateEntry: 'blank-create-entry',
  lobsterCreateEntry: 'lobster-create-entry',
  editorSettingsEntry: 'editor-settings-entry',
  editorBackHome: 'editor-back-home',
  editorCourseListenMode: 'editor-course-listen-mode',
  editorPublish: 'editor-publish',
} as const;

const GUIDE_COURSE_TARGET_PREFIX = `${ONBOARDING_TARGET_IDS.guideCourseCard}-`;

export type OnboardingTargetId =
  (typeof ONBOARDING_TARGET_IDS)[keyof typeof ONBOARDING_TARGET_IDS];

export const buildOnboardingTargetProps = (id: string) => ({
  [ONBOARDING_TARGET_ATTR]: id,
});

export const buildGuideCourseTargetId = (bid?: string | null) => {
  const normalizedBid = String(bid || '').trim();
  return normalizedBid
    ? `${GUIDE_COURSE_TARGET_PREFIX}${normalizedBid}`
    : ONBOARDING_TARGET_IDS.guideCourseCard;
};

const escapeAttributeValue = (value: string) => {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
    return CSS.escape(value);
  }
  return value;
};

export const getOnboardingTargetElement = (id?: string | null) => {
  if (typeof document === 'undefined' || !id) {
    return null;
  }

  const escapedId = escapeAttributeValue(id);
  if (escapedId !== id) {
    return document.querySelector<HTMLElement>(
      `[${ONBOARDING_TARGET_ATTR}="${escapedId}"]`,
    );
  }

  const elements = document.querySelectorAll<HTMLElement>(
    `[${ONBOARDING_TARGET_ATTR}]`,
  );
  return (
    Array.from(elements).find(
      element => element.getAttribute(ONBOARDING_TARGET_ATTR) === id,
    ) || null
  );
};
