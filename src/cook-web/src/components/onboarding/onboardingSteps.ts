import React from 'react';
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

const buildLobsterDescription = (
  t: Translate,
  courseCreatorUrl?: string | null,
): React.ReactNode => {
  const linkLabel = t('adminHome.lobsterCourse.descriptionLink');
  if (!courseCreatorUrl) {
    return `${t('adminHome.lobsterCourse.descriptionPrefix')}${linkLabel}${t(
      'adminHome.lobsterCourse.descriptionSuffix',
    )}`;
  }

  return React.createElement(
    React.Fragment,
    null,
    t('adminHome.lobsterCourse.descriptionPrefix'),
    React.createElement(
      'a',
      {
        href: courseCreatorUrl,
        target: '_blank',
        rel: 'noopener noreferrer',
        onClick: (event: React.MouseEvent<HTMLAnchorElement>) =>
          event.stopPropagation(),
        className:
          'inline font-medium text-blue-600 underline-offset-4 transition-colors hover:text-blue-700 hover:underline',
      },
      linkLabel,
    ),
    t('adminHome.lobsterCourse.descriptionSuffix'),
  );
};

export function buildAdminHomeOnboardingSteps({
  t,
  billingEnabled,
  courseCreatorUrl,
}: BuildAdminHomeStepsOptions): OnboardingStep[] {
  const steps: OnboardingStep[] = [
    {
      id: 'blank_course_creation',
      title: t('adminHome.blankCourse.title'),
      description: t('adminHome.blankCourse.description'),
      targetId: ONBOARDING_TARGET_IDS.blankCreateEntry,
      skipWhenTargetMissing: true,
    },
    {
      id: 'lobster_course_creation',
      title: t('adminHome.lobsterCourse.title'),
      description: buildLobsterDescription(t, courseCreatorUrl),
      targetId: ONBOARDING_TARGET_IDS.lobsterCreateEntry,
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
