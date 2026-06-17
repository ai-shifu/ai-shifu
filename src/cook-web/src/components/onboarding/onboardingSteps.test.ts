import { buildAdminHomeOnboardingSteps } from './onboardingSteps';
import { buildGuideCourseTargetId } from '@/lib/onboardingTargets';

const t = (key: string) => key;

describe('buildAdminHomeOnboardingSteps', () => {
  test('keeps billing entry steps when trial welcome is not granted', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: true,
      trialOffer: {
        enabled: true,
        status: 'ineligible',
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
        granted_at: null,
        expires_at: null,
        welcome_dialog_acknowledged_at: null,
      },
    });

    expect(steps.map(step => step.id)).toEqual([
      'billing_balance',
      'billing_upgrade',
      'guide_course',
      'course_creation_entry',
    ]);
  });

  test('shows trial welcome before fixed billing entry steps when granted', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: true,
      trialOffer: {
        enabled: true,
        status: 'granted',
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
      },
    });

    expect(steps.map(step => step.id)).toEqual([
      'welcome_trial',
      'billing_balance',
      'billing_upgrade',
      'guide_course',
      'course_creation_entry',
    ]);
  });

  test('targets the selected guide course bid instead of the first guide card', () => {
    const steps = buildAdminHomeOnboardingSteps({
      t,
      billingEnabled: false,
      guideCourseBid: 'guide-zh-bid',
    });

    expect(steps.find(step => step.id === 'guide_course')?.targetId).toBe(
      buildGuideCourseTargetId('guide-zh-bid'),
    );
  });
});
