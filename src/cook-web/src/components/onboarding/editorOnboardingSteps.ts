import type { OnboardingStep } from './onboardingTypes';

type Translate = (key: string, options?: Record<string, unknown>) => string;

type BuildCourseEditorStepsOptions = {
  t: Translate;
  targetIds: {
    backHome: string;
    settingsEntry: string;
    listenMode: string;
    publish: string;
  };
};

export function buildCourseEditorOnboardingSteps({
  t,
  targetIds,
}: BuildCourseEditorStepsOptions): OnboardingStep[] {
  return [
    {
      id: 'back_home',
      title: t('courseEditor.backHome.title'),
      description: t('courseEditor.backHome.description'),
      targetId: targetIds.backHome,
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
      id: 'course_settings_listen_mode',
      title: t('courseEditor.listenMode.title'),
      description: t('courseEditor.listenMode.description'),
      targetId: targetIds.listenMode,
      panel: 'shifu_settings',
      skipWhenTargetMissing: false,
      waitForTargetMs: 3000,
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
