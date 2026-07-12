import { buildStripeCourseReturnUrl } from './courseReturnUrl';

describe('buildStripeCourseReturnUrl', () => {
  test('uses the canonical course URL returned by the backend', () => {
    expect(
      buildStripeCourseReturnUrl(
        '/c/practical-ai-teaching-methods',
        'legacy-bid',
      ),
    ).toBe('/c/practical-ai-teaching-methods');
  });

  test('falls back to the encoded course BID for old payment responses', () => {
    expect(buildStripeCourseReturnUrl(undefined, 'legacy bid')).toBe(
      '/c/legacy%20bid',
    );
  });

  test('falls back to the custom-domain course root without course identity', () => {
    expect(buildStripeCourseReturnUrl()).toBe('/c');
  });
});
