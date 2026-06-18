import {
  buildCourseLearningUrl,
  buildLearningModeUrl,
} from './publishLearningMode';

describe('publish learning mode urls', () => {
  test('uses backend published url when it is available', () => {
    expect(
      buildCourseLearningUrl(
        'course-1',
        'https://app.ai-shifu.cn/c/published-course',
      ),
    ).toBe('https://app.ai-shifu.cn/c/published-course');
  });

  test('falls back to the course route when no published url exists yet', () => {
    expect(buildCourseLearningUrl('course 1')).toBe('/c/course%201');
  });

  test('sets mode and removes legacy listen query while preserving other url parts', () => {
    expect(
      buildLearningModeUrl(
        'https://app.ai-shifu.cn/c/course-1?listen=1&lessonid=lesson-2#outline',
        'classroom',
      ),
    ).toBe(
      'https://app.ai-shifu.cn/c/course-1?lessonid=lesson-2&mode=classroom#outline',
    );
  });

  test('resolves relative course urls with the provided origin', () => {
    expect(
      buildLearningModeUrl('/c/course-1', 'listen', 'https://host.test'),
    ).toBe('https://host.test/c/course-1?mode=listen');
  });
});
