import {
  normalizeLegacyListenModeInUrl,
  parseBooleanQueryParam,
  parseLearningModeQueryParam,
  requestClassroomBrowserFullscreen,
  setLearningModeInUrl,
} from './learningModeUrl';

const originalLocation = window.location;

describe('learningModeUrl', () => {
  const setMockLocation = (href: string) => {
    const url = new URL(href);
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        href: url.toString(),
        pathname: url.pathname,
        search: url.search,
        hash: url.hash,
      },
    });
  };
  const setFullscreenElement = (element: Element | null) => {
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: element,
    });
  };
  const setWebkitFullscreenElement = (element: Element | null) => {
    Object.defineProperty(document, 'webkitFullscreenElement', {
      configurable: true,
      value: element,
    });
  };

  beforeEach(() => {
    jest.restoreAllMocks();
    setFullscreenElement(null);
    setWebkitFullscreenElement(null);
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(document.documentElement, 'webkitRequestFullscreen', {
      configurable: true,
      value: undefined,
    });
    setMockLocation('http://localhost:3000/c/course-1?listen=true');
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('parses supported learning mode values', () => {
    expect(parseLearningModeQueryParam('read')).toBe('read');
    expect(parseLearningModeQueryParam('LISTEN')).toBe('listen');
    expect(parseLearningModeQueryParam('classroom')).toBe('classroom');
    expect(parseLearningModeQueryParam('present')).toBeNull();
  });

  it('parses legacy boolean query values including numeric listen params', () => {
    expect(parseBooleanQueryParam('true')).toBe(true);
    expect(parseBooleanQueryParam('1')).toBe(true);
    expect(parseBooleanQueryParam('false')).toBe(false);
    expect(parseBooleanQueryParam('0')).toBe(false);
    expect(parseBooleanQueryParam('listen')).toBeNull();
    expect(parseBooleanQueryParam(undefined)).toBeNull();
  });

  it('sets learning mode while preserving preview mode, hash, and removing legacy listen mode', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation(
      'http://localhost:3000/c/course-1?preview=true&listen=true#slide-2',
    );

    setLearningModeInUrl('classroom');

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?preview=true&mode=classroom#slide-2',
    );
  });

  it('writes read and listen modes through the unified mode query parameter', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation(
      'http://localhost:3000/c/course-1?preview=true&mode=classroom',
    );

    setLearningModeInUrl('read');

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?preview=true&mode=read',
    );

    setMockLocation('http://localhost:3000/c/course-1?listen=false');
    setLearningModeInUrl('listen');

    expect(replaceStateSpy).toHaveBeenLastCalledWith(
      window.history.state,
      '',
      '/c/course-1?mode=listen',
    );
  });

  it('normalizes legacy listen query params only when mode is absent', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation(
      'http://localhost:3000/c/course-1?preview=true&listen=true',
    );

    normalizeLegacyListenModeInUrl({
      listenModeParam: parseBooleanQueryParam('1'),
      urlModeParam: null,
    });

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?preview=true&mode=listen',
    );

    setMockLocation(
      'http://localhost:3000/c/course-1?mode=classroom&listen=false',
    );
    normalizeLegacyListenModeInUrl({
      listenModeParam: false,
      urlModeParam: 'classroom',
    });

    expect(replaceStateSpy).toHaveBeenCalledTimes(1);
  });

  it('normalizes legacy numeric listen query params to listen mode', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation('http://localhost:3000/c/course-1?listen=1');

    normalizeLegacyListenModeInUrl({
      listenModeParam: true,
      urlModeParam: null,
    });

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?mode=listen',
    );
  });

  it('normalizes legacy listen=false query params to read mode', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation('http://localhost:3000/c/course-1?listen=false');

    normalizeLegacyListenModeInUrl({
      listenModeParam: false,
      urlModeParam: null,
    });

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?mode=read',
    );
  });

  it('uses browser fullscreen when it is available', async () => {
    const requestFullscreen = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    });

    await expect(requestClassroomBrowserFullscreen()).resolves.toBe(true);
    expect(requestFullscreen).toHaveBeenCalled();
  });

  it('uses WebKit fullscreen state before requesting fullscreen again', async () => {
    const requestFullscreen = jest.fn().mockResolvedValue(undefined);
    setWebkitFullscreenElement(document.body);
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    });

    await expect(requestClassroomBrowserFullscreen()).resolves.toBe(true);
    expect(requestFullscreen).not.toHaveBeenCalled();
  });

  it('requests fullscreen on a provided target element', async () => {
    const targetElement = document.createElement('section');
    const requestFullscreen = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(targetElement, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    });

    await expect(
      requestClassroomBrowserFullscreen(targetElement),
    ).resolves.toBe(true);
    expect(requestFullscreen).toHaveBeenCalledTimes(1);
    expect(requestFullscreen.mock.contexts[0]).toBe(targetElement);
  });
});
