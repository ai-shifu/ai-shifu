import { buildCourseEditorOnboardingSteps } from './editorOnboardingSteps';

const t = (key: string) => key;

describe('buildCourseEditorOnboardingSteps', () => {
  test('returns the expected owner editor step order', () => {
    const steps = buildCourseEditorOnboardingSteps({
      t,
      targetIds: {
        settingsEntry: 'settings-entry',
        promptEdit: 'prompt-edit',
        debug: 'debug',
        addLesson: 'add-lesson',
        model: 'model',
        listenMode: 'listen-mode',
        price: 'price',
        preview: 'preview',
        publish: 'publish',
      },
    });

    expect(steps.map(step => step.id)).toEqual([
      'prompt_edit',
      'debug',
      'add_lesson',
      'course_settings_entry',
      'course_settings_model',
      'course_settings_listen_mode',
      'course_settings_price',
      'preview',
      'publish',
    ]);
    expect(
      steps.slice(4, 7).every(step => step.panel === 'shifu_settings'),
    ).toBe(true);
    expect(steps.slice(0, 4).every(step => !step.panel)).toBe(true);
  });
});
