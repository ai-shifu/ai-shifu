import {
  COURSE_EDITOR_ONBOARDING_INTENT_KEY,
  clearCourseEditorOnboardingIntent,
  getPendingCourseEditorOnboardingSource,
  markLobsterCourseEditorOnboardingIntent,
} from './courseEditorOnboardingIntent';

describe('course editor onboarding intent', () => {
  beforeEach(() => {
    window.localStorage.clear();
    jest.spyOn(Date, 'now').mockReturnValue(1_000_000);
  });

  afterEach(() => {
    jest.restoreAllMocks();
    window.localStorage.clear();
  });

  test('marks and reads a pending lobster create intent', () => {
    markLobsterCourseEditorOnboardingIntent();

    expect(getPendingCourseEditorOnboardingSource()).toBe('lobster_create');
  });

  test('clears invalid intent payloads', () => {
    window.localStorage.setItem(
      COURSE_EDITOR_ONBOARDING_INTENT_KEY,
      '{invalid',
    );

    expect(getPendingCourseEditorOnboardingSource()).toBe('');
    expect(
      window.localStorage.getItem(COURSE_EDITOR_ONBOARDING_INTENT_KEY),
    ).toBeNull();
  });

  test('expires stale pending intents', () => {
    markLobsterCourseEditorOnboardingIntent();
    (Date.now as jest.Mock).mockReturnValue(1_000_000 + 3 * 60 * 60 * 1000 + 1);

    expect(getPendingCourseEditorOnboardingSource()).toBe('');
    expect(
      window.localStorage.getItem(COURSE_EDITOR_ONBOARDING_INTENT_KEY),
    ).toBeNull();
  });

  test('clears pending intent explicitly', () => {
    markLobsterCourseEditorOnboardingIntent();

    clearCourseEditorOnboardingIntent();

    expect(getPendingCourseEditorOnboardingSource()).toBe('');
  });
});
