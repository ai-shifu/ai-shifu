import { buildAdminHomeOnboardingSteps } from './onboardingSteps';
import { ONBOARDING_TARGET_IDS } from '@/lib/onboardingTargets';
import { render, screen } from '@testing-library/react';
import React from 'react';

const t = (key: string) => {
  const translations: Record<string, string> = {
    'adminHome.billingCard.descriptionWithExpiry':
      'Trial {credits} expires on {expiresAt}',
    'adminHome.billingCard.descriptionWithDays':
      'Trial {credits} lasts {days} days',
    'adminHome.lobsterCourse.descriptionPrefix': 'Use ',
    'adminHome.lobsterCourse.descriptionLink': 'AI assistant',
    'adminHome.lobsterCourse.descriptionSuffix': ' to create faster.',
  };
  return translations[key] || key;
};

const trialOffer = {
  enabled: true,
  status: 'granted' as const,
  product_bid: 'trial',
  product_code: 'creator-plan-trial',
  display_name: 'Trial',
  description: 'Trial credits',
  currency: 'CNY',
  price_amount: 0,
  credit_amount: 100,
  valid_days: 15,
  highlights: [],
  starts_on_first_grant: true,
  granted_at: '2026-06-17T00:00:00Z',
  expires_at: '2026-07-02T00:00:00Z',
  welcome_dialog_acknowledged_at: null,
};

describe('buildAdminHomeOnboardingSteps', () => {
  test('builds the updated three-step admin home flow when billing is enabled', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: true,
      trialOffer,
      courseCreatorUrl: 'https://example.com/lobster',
      locale: 'en-US',
    });

    expect(steps.map(step => step.id)).toEqual([
      'blank_course_creation',
      'lobster_course_creation',
      'billing_card',
    ]);
    expect(steps.map(step => step.targetId)).toEqual([
      ONBOARDING_TARGET_IDS.blankCreateEntry,
      ONBOARDING_TARGET_IDS.lobsterCreateEntry,
      ONBOARDING_TARGET_IDS.billingCard,
    ]);
    expect(steps[1].actionHref).toBeUndefined();
    expect(steps[1].actionLabel).toBeUndefined();
    render(React.createElement('div', null, steps[1].description));
    expect(screen.getByRole('link', { name: 'AI assistant' })).toHaveAttribute(
      'href',
      'https://example.com/lobster',
    );
    expect(steps[2].description).toContain('100');
    expect(steps[2].highlightPadding).toBe(4);
  });

  test('omits the billing card step when billing is disabled', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: false,
      trialOffer,
      courseCreatorUrl: 'https://example.com/lobster',
    });

    expect(steps.map(step => step.id)).toEqual([
      'blank_course_creation',
      'lobster_course_creation',
    ]);
  });

  test('keeps the lobster step without an action when no creator url exists', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: false,
      courseCreatorUrl: null,
    });

    expect(steps[1].id).toBe('lobster_course_creation');
    expect(steps[1].actionHref).toBeUndefined();
    expect(steps[1].actionLabel).toBeUndefined();
  });
});
