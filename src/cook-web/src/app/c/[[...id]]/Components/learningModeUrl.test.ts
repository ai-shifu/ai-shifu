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

  beforeEach(() => {
    jest.restoreAllMocks();
    setMockLocation('http://localhost:3000/c/course-1?listen=true');
  });

  it('parses supported learning mode values', () => {
    expect(parseLearningModeQueryParam('read')).toBe('read');
    expect(parseLearningModeQueryParam('LISTEN')).toBe('listen');
    expect(parseLearningModeQueryParam('classroom')).toBe('classroom');
    expect(parseLearningModeQueryParam('present')).toBeNull();
  });

  it('enables classroom mode with preview and without legacy listen mode', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');

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
});
