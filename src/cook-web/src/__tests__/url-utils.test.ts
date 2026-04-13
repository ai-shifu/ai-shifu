import {
  buildLoginRedirectPath,
  buildUrlWithLessonId,
  replaceCurrentUrlWithLessonId,
} from '../c-utils/urlUtils';

describe('buildLoginRedirectPath', () => {
  it('removes WeChat OAuth params but keeps other query params', () => {
    const url =
      'https://example.com/c/123?code=wxcode&state=wxstate&channel=wechat&preview=true';
    expect(buildLoginRedirectPath(url)).toBe(
      '/c/123?channel=wechat&preview=true',
    );
  });

  it('returns pathname when only OAuth params are present', () => {
    const url = 'https://example.com/c/123?code=wxcode&state=wxstate';
    expect(buildLoginRedirectPath(url)).toBe('/c/123');
  });
});

describe('buildUrlWithLessonId', () => {
  it('adds lessonid while keeping other query params and hash', () => {
    const url = 'https://example.com/c/123?listen=1#course-outline';
    expect(buildUrlWithLessonId(url, 'lesson-2')).toBe(
      '/c/123?listen=1&lessonid=lesson-2#course-outline',
    );
  });

  it('replaces an existing lessonid with the latest selected lesson', () => {
    const url = 'https://example.com/c/123?lessonid=lesson-1&listen=1';
    expect(buildUrlWithLessonId(url, 'lesson-2')).toBe(
      '/c/123?lessonid=lesson-2&listen=1',
    );
  });

  it('removes lessonid when the provided value is empty', () => {
    const url = 'https://example.com/c/123?lessonid=lesson-1&listen=1';
    expect(buildUrlWithLessonId(url, '')).toBe('/c/123?listen=1');
  });
});

describe('replaceCurrentUrlWithLessonId', () => {
  it('replaces the browser url with the resolved lessonid', () => {
    window.history.replaceState({}, '', '/shifu/course-1?listen=1');
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');

    replaceCurrentUrlWithLessonId('lesson-3');

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/shifu/course-1?listen=1&lessonid=lesson-3',
    );

    replaceStateSpy.mockRestore();
  });

  it('skips history updates when lessonid is already in sync', () => {
    window.history.replaceState(
      {},
      '',
      '/shifu/course-1?listen=1&lessonid=lesson-3',
    );
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');

    replaceCurrentUrlWithLessonId('lesson-3');

    expect(replaceStateSpy).not.toHaveBeenCalled();

    replaceStateSpy.mockRestore();
  });
});
