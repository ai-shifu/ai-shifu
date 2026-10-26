import {
  buildCourseLearningUrl,
  buildLearningModeUrl,
  buildParameterlessCourseUrl,
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

  test('builds a learning-mode url from a stripped course link', () => {
    expect(
      buildLearningModeUrl(
        `${TEST_ORIGIN}/c/course-1?listen=1&lessonid=lesson-2#outline`,
        'classroom',
      ),
    ).toBe(`${TEST_ORIGIN}/c/course-1?mode=classroom`);
  });

  test('resolves relative course urls with the provided origin', () => {
    expect(
      buildLearningModeUrl('/c/course-1', 'listen', 'https://host.test'),
    ).toBe('https://host.test/c/course-1?mode=listen');
  });

  test('strips query params and hash from absolute published urls', () => {
    expect(
      buildParameterlessCourseUrl(
        `${TEST_ORIGIN}/c/course-1?mode=classroom&lessonid=lesson-2#outline`,
      ),
    ).toBe(`${TEST_ORIGIN}/c/course-1`);
  });

  test('strips query params from relative published urls', () => {
    expect(
      buildParameterlessCourseUrl(
        '/c/course-1?listen=1&preview=true',
        'https://host.test',
      ),
    ).toBe('/c/course-1');
  });

  test('returns an empty string for blank published urls', () => {
    expect(buildParameterlessCourseUrl('   ')).toBe('');
  });

  test('rejects javascript and data urls without a learning mode', () => {
    expect(buildParameterlessCourseUrl('javascript:alert(1)')).toBe('');
    expect(
      buildParameterlessCourseUrl('data:text/html,<script>alert(1)</script>'),
    ).toBe('');
  });

  test('rejects javascript and data urls when adding a learning mode', () => {
    expect(buildLearningModeUrl('javascript:alert(1)', 'listen')).toBe('');
    expect(
      buildLearningModeUrl('data:text/html,<script>alert(1)</script>', 'read'),
    ).toBe('');
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
