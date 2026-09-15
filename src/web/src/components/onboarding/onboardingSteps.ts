import { ONBOARDING_TARGET_IDS } from '@/lib/onboardingTargets';
import type { OnboardingStep } from './onboardingTypes';

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * - 'module.onboarding.adminHome.billingCard.descriptionGeneric'
 */

type Translate = (key: string, options?: Record<string, unknown>) => string;

type BuildAdminHomeStepsOptions = {
  t: Translate;
  billingEnabled: boolean;
  courseCreatorUrl?: string | null;
};

const buildBillingDescription = (t: Translate) => {
  return t('adminHome.billingCard.descriptionGeneric');
};

export function buildAdminHomeOnboardingSteps({
  t,
  billingEnabled,
}: BuildAdminHomeStepsOptions): OnboardingStep[] {
  const steps: OnboardingStep[] = [
    {
      id: 'course_creation_choice',
      title: t('adminHome.courseCreationChoice.title'),
      description: t('adminHome.courseCreationChoice.description'),
      targetId: ONBOARDING_TARGET_IDS.courseCreationEntry,
      skipWhenTargetMissing: true,
    },
  ];

  if (billingEnabled) {
    steps.push({
      id: 'billing_card',
      title: t('adminHome.billingCard.title'),
      description: buildBillingDescription(t),
      targetId: ONBOARDING_TARGET_IDS.billingCard,
      skipWhenTargetMissing: true,
      highlightPadding: 4,
    });
  }

  return steps;
}
