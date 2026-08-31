import {
  buildProfileAssistantAttemptAnalytics,
  buildProfileAssistantResultAnalytics,
  buildProfileCollectionRouteAnalytics,
} from './profileOnboardingAnalytics';

describe('profileOnboardingAnalytics', () => {
  test('builds a low-cardinality route choice payload', () => {
    expect(
      buildProfileCollectionRouteAnalytics({
        intent: 'onboarding',
        presentation: 'blocking',
        route: 'ai_assistant',
      }),
    ).toEqual({
      source: 'guided',
      presentation: 'blocking',
      route: 'ai_assistant',
    });
  });

  test('builds attempt and terminal result payloads without profile content', () => {
    expect(
      buildProfileAssistantAttemptAnalytics({
        intent: 'settings',
        presentation: 'hidden',
      }),
    ).toEqual({ source: 'settings', presentation: 'hidden' });

    const payload = buildProfileAssistantResultAnalytics({
      intent: 'settings',
      presentation: 'hidden',
      outcome: 'failed',
      failureCategory: 'runtime_failed',
    });
    expect(payload).toEqual({
      source: 'settings',
      presentation: 'hidden',
      outcome: 'failed',
      failure_category: 'runtime_failed',
    });
    expect(payload).not.toHaveProperty('prompt');
    expect(payload).not.toHaveProperty('raw_text');
    expect(payload).not.toHaveProperty('profile');
    expect(payload).not.toHaveProperty('error');
  });
});
