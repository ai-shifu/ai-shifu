import { resolveCourseLearningMode } from './learningModePreference';

describe('resolveCourseLearningMode', () => {
  it('keeps read when the course supports listen mode and no storage exists yet', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
        canUseClassroomMode: false,
        hasListenModeOverride: false,
        listenModeParam: null,
        storedLearningMode: null,
      }),
    ).toBe('read');
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

  it('respects a classroom URL mode only when preview access is available', () => {
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
});
