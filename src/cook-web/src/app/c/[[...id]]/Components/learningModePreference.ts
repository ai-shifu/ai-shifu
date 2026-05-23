import type { LearningMode } from './learningModeOptions';

type ResolveCourseLearningModeArgs = {
  courseTtsEnabled: boolean | null;
  hasListenModeOverride: boolean;
  listenModeParam: boolean | null;
  storedLearningMode: LearningMode | null;
};

export const resolveCourseLearningMode = ({
  courseTtsEnabled,
  hasListenModeOverride,
  listenModeParam,
  storedLearningMode,
}: ResolveCourseLearningModeArgs): LearningMode => {
  if (hasListenModeOverride) {
    if (courseTtsEnabled === null) {
      return listenModeParam === true ? 'listen' : 'read';
    }

    return listenModeParam === true && courseTtsEnabled === true
      ? 'listen'
      : 'read';
  }

  if (storedLearningMode === 'listen' && courseTtsEnabled !== false) {
    return 'listen';
  }

  if (storedLearningMode === 'read') {
    return 'read';
  }

  return 'read';
};
