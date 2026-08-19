import type { LearningMode } from './learningModeOptions';

type ResolveCourseLearningModeArgs = {
  courseTtsEnabled: boolean | null;
  canUseClassroomMode: boolean | null;
  hasListenModeOverride: boolean;
  listenModeParam: boolean | null;
  urlModeParam?: LearningMode | null;
  storedLearningMode: LearningMode | null;
};

export const resolveCourseLearningMode = ({
  courseTtsEnabled,
  canUseClassroomMode,
  hasListenModeOverride,
  listenModeParam,
  urlModeParam = null,
  storedLearningMode,
}: ResolveCourseLearningModeArgs): LearningMode => {
  if (urlModeParam === 'classroom') {
    return canUseClassroomMode === false ? 'read' : 'classroom';
  }

  if (urlModeParam === 'listen') {
    return courseTtsEnabled !== false ? 'listen' : 'read';
  }

  if (urlModeParam === 'read') {
    return 'read';
  }

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

  if (storedLearningMode === 'classroom') {
    return canUseClassroomMode === true ? 'classroom' : 'read';
  }

  if (storedLearningMode === 'read') {
    return 'read';
  }

  return 'read';
};
