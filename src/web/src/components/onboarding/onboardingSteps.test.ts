import { buildAdminHomeOnboardingSteps } from './onboardingSteps';
import { ONBOARDING_TARGET_IDS } from '@/lib/onboardingTargets';
const t = (key: string) => {
  const translations: Record<string, string> = {
    'adminHome.billingCard.descriptionGeneric':
      'Check balance or buy and upgrade plans',
    'adminHome.courseCreationChoice.description':
      'Choose AI-assisted or manual creation.',
  };
  return translations[key] || key;
};

describe('buildAdminHomeOnboardingSteps', () => {
  test('builds the course-choice and billing admin home flow', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: true,
      courseCreatorUrl: 'https://example.com/lobster',
    });

    expect(steps.map(step => step.id)).toEqual([
      'course_creation_choice',
      'billing_card',
    ]);
    expect(steps.map(step => step.targetId)).toEqual([
      ONBOARDING_TARGET_IDS.courseCreationEntry,
      ONBOARDING_TARGET_IDS.billingCard,
    ]);
    expect(steps[0].description).toBe('Choose AI-assisted or manual creation.');
    expect(steps[1].description).toBe('Check balance or buy and upgrade plans');
    expect(steps[1].highlightPadding).toBe(4);
  });

  test('omits the billing card step when billing is disabled', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: false,
      courseCreatorUrl: 'https://example.com/lobster',
    });

    expect(steps.map(step => step.id)).toEqual(['course_creation_choice']);
  });

  test('uses generic billing copy for the billing card step', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: true,
    });

    expect(steps[1].description).toBe('Check balance or buy and upgrade plans');
  });
});
