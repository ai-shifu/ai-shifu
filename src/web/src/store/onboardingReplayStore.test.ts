import { useOnboardingReplayStore } from './onboardingReplayStore';

describe('useOnboardingReplayStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useOnboardingReplayStore.setState({
      replayScenes: { course_editor_onboarding: false },
    });
  });

  test('requests replay only for the retained course editor onboarding', () => {
    useOnboardingReplayStore.getState().requestReplayAll();

    expect(useOnboardingReplayStore.getState().replayScenes).toEqual({
      course_editor_onboarding: true,
    });
    expect(
      JSON.parse(localStorage.getItem('onboarding-replay-scenes') || ''),
    ).toEqual({ course_editor_onboarding: true });
  });
});
