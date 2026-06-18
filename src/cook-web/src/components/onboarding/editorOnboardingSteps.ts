import type { OnboardingStep } from './onboardingTypes';

type Translate = (key: string, options?: Record<string, unknown>) => string;

type BuildCourseEditorStepsOptions = {
  t: Translate;
  targetIds: {
    settingsEntry: string;
    promptEdit: string;
    debug: string;
    addLesson: string;
    model: string;
    listenMode: string;
    price: string;
    preview: string;
    publish: string;
  };
};

export function buildCourseEditorOnboardingSteps({
  t,
  targetIds,
}: BuildCourseEditorStepsOptions): OnboardingStep[] {
  return [
    {
      id: 'prompt_edit',
      title: t('courseEditor.prompt.title'),
      description: t('courseEditor.prompt.description'),
      targetId: targetIds.promptEdit,
      skipWhenTargetMissing: true,
      waitForTargetMs: 800,
    },
    {
      id: 'debug',
      title: t('courseEditor.debug.title'),
      description: t('courseEditor.debug.description'),
      targetId: targetIds.debug,
      skipWhenTargetMissing: true,
      waitForTargetMs: 800,
    },
    {
      id: 'add_lesson',
      title: t('courseEditor.addLesson.title'),
      description: t('courseEditor.addLesson.description'),
      targetId: targetIds.addLesson,
      skipWhenTargetMissing: true,
      waitForTargetMs: 800,
    },
    {
      id: 'course_settings_entry',
      title: t('courseEditor.settingsEntry.title'),
      description: t('courseEditor.settingsEntry.description'),
      targetId: targetIds.settingsEntry,
      skipWhenTargetMissing: true,
      waitForTargetMs: 800,
    },
    {
      id: 'course_settings_model',
      title: t('courseEditor.model.title'),
      description: t('courseEditor.model.description'),
      targetId: targetIds.model,
      panel: 'shifu_settings',
      skipWhenTargetMissing: true,
      waitForTargetMs: 1400,
    },
    {
      id: 'course_settings_listen_mode',
      title: t('courseEditor.listenMode.title'),
      description: t('courseEditor.listenMode.description'),
      targetId: targetIds.listenMode,
      panel: 'shifu_settings',
      skipWhenTargetMissing: true,
      waitForTargetMs: 1400,
    },
    {
      id: 'course_settings_price',
      title: t('courseEditor.price.title'),
      description: t('courseEditor.price.description'),
      targetId: targetIds.price,
      panel: 'shifu_settings',
      skipWhenTargetMissing: true,
      waitForTargetMs: 1400,
    },
    {
      id: 'preview',
      title: t('courseEditor.preview.title'),
      description: t('courseEditor.preview.description'),
      targetId: targetIds.preview,
      skipWhenTargetMissing: true,
      waitForTargetMs: 1000,
    },
    {
      id: 'publish',
      title: t('courseEditor.publish.title'),
      description: t('courseEditor.publish.description'),
      targetId: targetIds.publish,
      skipWhenTargetMissing: true,
      waitForTargetMs: 1000,
    },
  ];
}
