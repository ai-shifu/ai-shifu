import type { BillingTrialOffer } from '@/types/billing';
import {
  buildGuideCourseTargetId,
  ONBOARDING_TARGET_IDS,
} from '@/lib/onboardingTargets';
import React from 'react';
import type { OnboardingStep } from './onboardingTypes';

const replaceTemplate = (
  template: string,
  values: Record<string, string | number>,
) => {
  return Object.entries(values).reduce((result, [key, value]) => {
    return result.replaceAll(`{${key}}`, String(value));
  }, template);
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

const buildCourseCreationDescription = (t: Translate) => (
  React.createElement(
    React.Fragment,
    null,
    t('adminHome.courseCreation.descriptionPrefix'),
    React.createElement(
      'strong',
      null,
      t('adminHome.courseCreation.descriptionEmphasis'),
    ),
    t('adminHome.courseCreation.descriptionSuffix'),
  )
);

type BuildAdminHomeStepsOptions = {
  t: Translate;
  billingEnabled: boolean;
  trialOffer?: BillingTrialOffer | null;
  guideCourseBid?: string | null;
};

export function buildAdminHomeOnboardingSteps({
  t,
  billingEnabled,
  trialOffer,
  guideCourseBid,
}: BuildAdminHomeStepsOptions): OnboardingStep[] {
  const steps: OnboardingStep[] = [];
  const grantedTrial = billingEnabled && trialOffer?.status === 'granted';

  if (grantedTrial) {
    steps.push({
      id: 'welcome_trial',
      title: t('adminHome.welcome.title'),
      description: replaceTemplate(
        t('adminHome.welcome.description'),
        {
          credits: trialOffer?.credit_amount || 0,
          days: trialOffer?.valid_days || 0,
        },
      ),
    });
  }

  if (billingEnabled) {
    steps.push(
      {
        id: 'billing_balance',
        title: t('adminHome.balance.title'),
        description: t('adminHome.balance.description'),
        targetId: ONBOARDING_TARGET_IDS.billingBalance,
        skipWhenTargetMissing: true,
      },
      {
        id: 'billing_upgrade',
        title: t('adminHome.upgrade.title'),
        description: t('adminHome.upgrade.description'),
        targetId: ONBOARDING_TARGET_IDS.billingUpgrade,
        skipWhenTargetMissing: true,
      },
    );
  }

  steps.push(
    {
      id: 'guide_course',
      title: t('adminHome.guideCourse.title'),
      description: t('adminHome.guideCourse.description'),
      targetId: buildGuideCourseTargetId(guideCourseBid),
      skipWhenTargetMissing: true,
      waitForTargetMs: 700,
    },
    {
      id: 'course_creation_entry',
      title: t('adminHome.courseCreation.title'),
      description: buildCourseCreationDescription(t),
      targetId: ONBOARDING_TARGET_IDS.courseCreationEntry,
      skipWhenTargetMissing: true,
    },
  );

  return steps;
}
