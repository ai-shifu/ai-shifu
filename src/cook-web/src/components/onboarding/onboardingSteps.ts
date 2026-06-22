import React from 'react';
import type { BillingTrialOffer } from '@/types/billing';
import { ONBOARDING_TARGET_IDS } from '@/lib/onboardingTargets';
import { formatBillingDate } from '@/lib/billing';
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

type BuildAdminHomeStepsOptions = {
  t: Translate;
  billingEnabled: boolean;
  trialOffer?: BillingTrialOffer | null;
  courseCreatorUrl?: string | null;
  locale?: string;
};

const buildBillingDescription = (
  t: Translate,
  trialOffer: BillingTrialOffer | null | undefined,
  locale?: string,
) => {
  const credits = trialOffer?.credit_amount || 0;
  const expiresAt = formatBillingDate(
    trialOffer?.expires_at,
    locale || 'zh-CN',
  );
  const days = trialOffer?.valid_days || 0;
  const key = expiresAt
    ? 'adminHome.billingCard.descriptionWithExpiry'
    : 'adminHome.billingCard.descriptionWithDays';

  return replaceTemplate(t(key), {
    credits,
    expiresAt,
    days,
  });
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
  trialOffer,
  courseCreatorUrl,
  locale,
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
      description: buildBillingDescription(t, trialOffer, locale),
      targetId: ONBOARDING_TARGET_IDS.billingCard,
      skipWhenTargetMissing: true,
      highlightPadding: 4,
    });
  }

  return steps;
}
