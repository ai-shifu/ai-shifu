import {
  resolveCourseLearningMode,
  resolveCourseLearningModeState,
} from './learningModePreference';

describe('resolveCourseLearningMode', () => {
  it('defaults to listen when the course supports listen mode and no storage exists yet', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: null,
      }),
    ).toBe('listen');
  });

  it('keeps read when the course listen capability is still unknown', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: null,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: null,
      }),
    ).toBe('read');
  });

  it('keeps read when the course does not support listen mode', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: false,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: null,
      }),
    ).toBe('read');
  });

  it('respects an explicit stored read preference', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: 'read',
      }),
    ).toBe('read');
  });

  it('keeps url override higher priority than the auto default', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: false,
        hasListenModeOverride: true,
        listenModeParam: false,
        storedLearningMode: null,
      }),
    ).toBe('read');
  });

  it('respects a classroom URL mode unless access is denied', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: false,
        canUseClassroomMode: true,
        hasListenModeOverride: false,
        listenModeParam: null,
        urlModeParam: 'classroom',
        storedLearningMode: 'listen',
      }),
    ).toBe('classroom');

    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: null,
        hasListenModeOverride: false,
        listenModeParam: null,
        urlModeParam: 'classroom',
        storedLearningMode: 'listen',
      }),
    ).toBe('classroom');

    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        urlModeParam: 'classroom',
        storedLearningMode: 'listen',
      }),
    ).toBe('read');
  });

  it('respects explicit URL read and listen modes before storage', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: true,
        hasListenModeOverride: false,
        listenModeParam: null,
        urlModeParam: 'listen',
        storedLearningMode: 'read',
      }),
    ).toBe('listen');

    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: true,
        hasListenModeOverride: false,
        listenModeParam: null,
        urlModeParam: 'read',
        storedLearningMode: 'listen',
      }),
    ).toBe('read');
  });

  it('keeps URL listen mode while course TTS capability is still unknown', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: null,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        urlModeParam: 'listen',
        storedLearningMode: 'read',
      }),
    ).toBe('listen');
  });

  it('falls back from URL listen mode when course TTS is disabled', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: false,
        canUseClassroomMode: true,
        hasListenModeOverride: false,
        listenModeParam: null,
        urlModeParam: 'listen',
        storedLearningMode: 'listen',
      }),
    ).toBe('read');
  });

  it('restores stored classroom mode only when classroom access is available', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: true,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: 'classroom',
      }),
    ).toBe('classroom');

    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: 'classroom',
      }),
    ).toBe('read');

    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: null,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: 'classroom',
      }),
    ).toBe('read');
  });
});

describe('resolveCourseLearningModeState', () => {
  it('waits for course TTS before resolving an automatic default', () => {
    expect(
      resolveCourseLearningModeState({
        courseId: 'course-1',
        currentLearningMode: 'read',
        courseTtsEnabled: null,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: null,
      }),
    ).toEqual({
      shouldWaitForLearningModeResolution: true,
      resolvedLearningMode: null,
      isLearningModeReady: false,
    });
  });

  it('keeps chat loading paused until the resolved default is applied', () => {
    expect(
      resolveCourseLearningModeState({
        courseId: 'course-1',
        currentLearningMode: 'read',
        courseTtsEnabled: true,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: null,
      }),
    ).toEqual({
      shouldWaitForLearningModeResolution: false,
      resolvedLearningMode: 'listen',
      isLearningModeReady: false,
    });
  });

  it('does not block rendering while resolution is disabled', () => {
    expect(
      resolveCourseLearningModeState({
        courseId: 'course-1',
        currentLearningMode: 'read',
        isResolutionEnabled: false,
        courseTtsEnabled: null,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: null,
      }),
    ).toEqual({
      shouldWaitForLearningModeResolution: false,
      resolvedLearningMode: 'read',
      isLearningModeReady: true,
    });
  });
});
