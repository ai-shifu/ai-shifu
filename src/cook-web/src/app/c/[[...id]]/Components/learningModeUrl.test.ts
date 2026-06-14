import {
  clearClassroomModeFromUrl,
  enableClassroomModeInUrl,
  parseLearningModeQueryParam,
  requestClassroomBrowserFullscreen,
} from './learningModeUrl';

describe('learningModeUrl', () => {
  const setMockLocation = (href: string) => {
    const url = new URL(href);
    window.location.href = url.toString();
    window.location.pathname = url.pathname;
    window.location.search = url.search;
    window.location.hash = url.hash;
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

  it('parses supported learning mode values', () => {
    expect(parseLearningModeQueryParam('read')).toBe('read');
    expect(parseLearningModeQueryParam('LISTEN')).toBe('listen');
    expect(parseLearningModeQueryParam('classroom')).toBe('classroom');
    expect(parseLearningModeQueryParam('present')).toBeNull();
  });

  it('enables classroom mode while preserving preview mode and removing legacy listen mode', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation(
      'http://localhost:3000/c/course-1?preview=true&listen=true',
    );

    enableClassroomModeInUrl();

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?preview=true&mode=classroom',
    );
  });

  it('clears only the classroom mode query parameter', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation(
      'http://localhost:3000/c/course-1?preview=true&mode=classroom',
    );

    clearClassroomModeFromUrl();

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?preview=true',
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
