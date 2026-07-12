import {
  buildCoursePageUrl,
  buildLoginRedirectPath,
  buildUrlWithLessonId,
  getCourseCreatorUrl,
  getPaymentAgreementUrl,
  replaceCurrentUrlWithLessonId,
} from '../c-utils/urlUtils';

const originalLocation = window.location;

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

describe('buildCoursePageUrl', () => {
  it('keeps the current origin and course path without lesson state', () => {
    expect(
      buildCoursePageUrl(
        'https://learn.example.com/c/course-1?lessonid=lesson-1&mode=classroom&preview=true#follow-up',
      ),
    ).toBe('https://learn.example.com/c/course-1');
  });

  it('preserves custom domains and their current course path', () => {
    expect(
      buildCoursePageUrl(
        'https://course.example.com/c?lessonid=lesson-1&listen=1',
      ),
    ).toBe('https://course.example.com/c');
  });

  it('preserves localhost ports', () => {
    expect(
      buildCoursePageUrl('http://localhost:3000/c/course-1?lessonid=lesson-1'),
    ).toBe('http://localhost:3000/c/course-1');
  });

  it('removes basic authentication credentials', () => {
    expect(
      buildCoursePageUrl(
        'https://teacher:secret@learn.example.com/c/course-1?lessonid=lesson-1',
      ),
    ).toBe('https://learn.example.com/c/course-1');
  });

  it.each(['not a url', 'mailto:teacher@example.com'])(
    'rejects invalid course page urls: %s',
    currentUrl => {
      expect(buildCoursePageUrl(currentUrl)).toBe('');
    },
  );
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
  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('replaces the browser url with the resolved lessonid', () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        href: 'http://localhost/shifu/course-1?listen=1',
        pathname: '/shifu/course-1',
        search: '?listen=1',
        hash: '',
      },
    });
    const replaceStateSpy = jest
      .spyOn(window.history, 'replaceState')
      .mockImplementation(() => undefined);

    replaceCurrentUrlWithLessonId('lesson-3');

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/shifu/course-1?listen=1&lessonid=lesson-3',
    );

    replaceStateSpy.mockRestore();
  });

  it('skips history updates when lessonid is already in sync', () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        href: 'http://localhost/shifu/course-1?listen=1&lessonid=lesson-3',
        pathname: '/shifu/course-1',
        search: '?listen=1&lessonid=lesson-3',
        hash: '',
      },
    });
    const replaceStateSpy = jest
      .spyOn(window.history, 'replaceState')
      .mockImplementation(() => undefined);

    replaceCurrentUrlWithLessonId('lesson-3');

    expect(replaceStateSpy).not.toHaveBeenCalled();

    replaceStateSpy.mockRestore();
  });
});

describe('domain aware urls', () => {
  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('returns the cn course creator deep link on ai-shifu.cn hosts', () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        hostname: 'app.ai-shifu.cn',
      },
    });

    expect(getCourseCreatorUrl()).toBe(
      'https://zhentouai.feishu.cn/wiki/AUE5wpipJi5bL4k6GticmxddnPb?from=from_copylink',
    );
  });

  it('keeps the existing educators page url on ai-shifu.com hosts', () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        hostname: 'app.ai-shifu.com',
      },
    });

    expect(getCourseCreatorUrl()).toBe(
      'https://ai-shifu.com/educators.html#course-creator-skill',
    );
  });

  it('resolves payment agreement urls from the detected host domain', () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        hostname: 'app.ai-shifu.com',
      },
    });

    expect(getPaymentAgreementUrl()).toBe(
      'https://ai-shifu.com/payment-agreement.html',
    );
  });
});
