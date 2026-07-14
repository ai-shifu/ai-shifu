import { buildCanonicalCourseRouteUrl, buildCoursePageUrl } from './urlUtils';

describe('course route urls', () => {
  test('replaces only the course path and preserves query parameters and hash', () => {
    expect(
      buildCanonicalCourseRouteUrl(
        'https://example.test/c/legacy-bid?lessonid=lesson-1&mode=listen&preview=true#follow-up',
        '/c/practical-ai-teaching-methods',
      ),
    ).toBe(
      '/c/practical-ai-teaching-methods?lessonid=lesson-1&mode=listen&preview=true#follow-up',
    );
  });

  test('keeps a custom-domain root course route unchanged without a canonical target', () => {
    expect(
      buildCanonicalCourseRouteUrl(
        'https://course.example.test/c?lessonid=lesson-1#follow-up',
        '',
      ),
    ).toBe('/c?lessonid=lesson-1#follow-up');
  });

  test('builds a query-free absolute canonical URL for the PDF QR code', () => {
    expect(
      buildCoursePageUrl(
        'https://example.test/c/legacy-bid?preview=true#lesson',
        '/c/practical-ai-teaching-methods?preview=true',
      ),
    ).toBe('https://example.test/c/practical-ai-teaching-methods');
  });

  test('does not replace the current route with a non-course backend path', () => {
    expect(
      buildCanonicalCourseRouteUrl(
        'https://example.test/c/legacy-bid?lessonid=lesson-1',
        '/admin/shifu-1',
      ),
    ).toBe('/c/legacy-bid?lessonid=lesson-1');
  });
});
