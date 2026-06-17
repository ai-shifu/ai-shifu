export const ONBOARDING_TARGET_ATTR = 'data-onboarding-id';

export const ONBOARDING_TARGET_IDS = {
  billingBalance: 'billing-balance',
  billingUpgrade: 'billing-upgrade',
  guideCourseCard: 'guide-course-card',
  courseCreationEntry: 'course-creation-entry',
  blankCreateEntry: 'blank-create-entry',
  lobsterCreateEntry: 'lobster-create-entry',
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
  return value.replace(/"/g, '\\"');
};

export const getOnboardingTargetElement = (id?: string | null) => {
  if (typeof document === 'undefined' || !id) {
    return null;
  }

  return document.querySelector<HTMLElement>(
    `[${ONBOARDING_TARGET_ATTR}="${escapeAttributeValue(id)}"]`,
  );
};
