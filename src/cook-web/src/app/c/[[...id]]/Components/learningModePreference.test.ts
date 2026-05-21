import { resolveCourseLearningMode } from './learningModePreference';

describe('resolveCourseLearningMode', () => {
  it('keeps read when the course supports listen mode and no storage exists yet', () => {
    expect(
      resolveCourseLearningMode({
        courseTtsEnabled: true,
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
        hasListenModeOverride: true,
        listenModeParam: false,
        storedLearningMode: null,
      }),
    ).toBe('read');
  });
});
