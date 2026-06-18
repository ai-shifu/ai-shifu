import {
  buildCourseLearningUrl,
  buildLearningModeUrl,
  isPublishLearningModeAvailable,
} from './publishLearningMode';

describe('publish learning mode urls', () => {
  const TEST_ORIGIN = 'https://example.test';

  test('uses backend published url when it is available', () => {
    expect(
      buildCourseLearningUrl('course-1', `${TEST_ORIGIN}/c/published-course`),
    ).toBe(`${TEST_ORIGIN}/c/published-course`);
  });

  test('falls back to the course route when no published url exists yet', () => {
    expect(buildCourseLearningUrl('course 1')).toBe('/c/course%201');
  });

  test('sets mode and removes legacy listen query while preserving other url parts', () => {
    expect(
      buildLearningModeUrl(
        `${TEST_ORIGIN}/c/course-1?listen=1&lessonid=lesson-2#outline`,
        'classroom',
      ),
    ).toBe(
      `${TEST_ORIGIN}/c/course-1?lessonid=lesson-2&mode=classroom#outline`,
    );
  });

  test('resolves relative course urls with the provided origin', () => {
    expect(
      buildLearningModeUrl('/c/course-1', 'listen', 'https://host.test'),
    ).toBe('https://host.test/c/course-1?mode=listen');
  });

  test('disables listen publish links only when tts is disabled', () => {
    expect(
      isPublishLearningModeAvailable({
        mode: 'listen',
        ttsEnabled: false,
      }),
    ).toBe(false);
    expect(
      isPublishLearningModeAvailable({
        mode: 'listen',
        ttsEnabled: true,
      }),
    ).toBe(true);
    expect(
      isPublishLearningModeAvailable({
        mode: 'listen',
        ttsEnabled: null,
      }),
    ).toBe(true);
  });

  test('keeps read and classroom publish links available without tts', () => {
    expect(
      isPublishLearningModeAvailable({
        mode: 'read',
        ttsEnabled: false,
      }),
    ).toBe(true);
    expect(
      isPublishLearningModeAvailable({
        mode: 'classroom',
        ttsEnabled: false,
      }),
    ).toBe(true);
  });
});
