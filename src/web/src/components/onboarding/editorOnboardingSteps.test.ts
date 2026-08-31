import { buildCourseEditorOnboardingSteps } from './editorOnboardingSteps';

const t = (key: string) => key;

describe('buildCourseEditorOnboardingSteps', () => {
  test('returns the expected owner editor step order', () => {
    const steps = buildCourseEditorOnboardingSteps({
      t,
      targetIds: {
        backHome: 'back-home',
        settingsEntry: 'settings-entry',
        listenMode: 'listen-mode',
        publish: 'publish',
      },
    });

    expect(steps.map(step => step.id)).toEqual([
      'back_home',
      'course_settings_entry',
      'course_settings_listen_mode',
      'publish',
    ]);
    expect(steps[2].panel).toBe('shifu_settings');
    expect([steps[0], steps[1], steps[3]].every(step => !step.panel)).toBe(
      true,
    );
  });
});
