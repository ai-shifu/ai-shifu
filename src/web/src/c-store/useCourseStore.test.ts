import { useCourseStore } from './useCourseStore';

jest.mock('sse.js', () => ({
  SSE: jest.fn(),
}));

jest.mock('@/c-api/lesson', () => ({
  resetChapter: jest.fn(),
}));

describe('useCourseStore course description', () => {
  afterEach(() => {
    useCourseStore.getState().updateCourseDescription('');
  });

  it('starts empty and exposes a focused description updater', () => {
    expect(useCourseStore.getInitialState().courseDescription).toBe('');

    useCourseStore
      .getState()
      .updateCourseDescription('A learner-facing course description');

    expect(useCourseStore.getState().courseDescription).toBe(
      'A learner-facing course description',
    );
  });
});
