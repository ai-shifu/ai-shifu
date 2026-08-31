import { redirectToHomeUrlIfRootPath } from './utils';

const originalLocation = window.location;

describe('redirectToHomeUrlIfRootPath', () => {
  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('redirects the root path to the admin fallback', () => {
    const replace = jest.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        href: 'https://app.example.com/',
        pathname: '/',
        replace,
      },
    });

    expect(redirectToHomeUrlIfRootPath('/admin')).toBe(true);
    expect(replace).toHaveBeenCalledWith('/admin');
  });

  it('redirects the course entry path to a course configured as HOME_URL', () => {
    const replace = jest.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        href: 'https://app.example.com/c',
        pathname: '/c',
        replace,
      },
    });

    expect(redirectToHomeUrlIfRootPath('/c/course-1')).toBe(true);
    expect(replace).toHaveBeenCalledWith('/c/course-1');
  });

  it.each([
    ['https://app.example.com/', '/'],
    ['https://app.example.com/c', '/c'],
  ])(
    'redirects %s to a course configured through a legacy HOME_URL query',
    (href, pathname) => {
      const replace = jest.fn();
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: {
          href,
          pathname,
          replace,
        },
      });

      const homeUrl = '/c?courseId=course-1&lessonid=lesson-1';
      expect(redirectToHomeUrlIfRootPath(homeUrl)).toBe(true);
      expect(replace).toHaveBeenCalledWith(homeUrl);
    },
  );

  it('does not redirect a legacy course query target to itself', () => {
    const replace = jest.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        href: 'https://app.example.com/c?courseId=course-1',
        pathname: '/c',
        replace,
      },
    });

    expect(redirectToHomeUrlIfRootPath('/c?courseId=course-1')).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });

  it('redirects the course entry path to a configured root HOME_URL', () => {
    const replace = jest.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        href: 'https://app.example.com/c',
        pathname: '/c',
        replace,
      },
    });

    expect(redirectToHomeUrlIfRootPath('/')).toBe(true);
    expect(replace).toHaveBeenCalledWith('/');
  });

  it('does not redirect the root path to itself', () => {
    const replace = jest.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        href: 'https://app.example.com/',
        pathname: '/',
        replace,
      },
    });

    expect(redirectToHomeUrlIfRootPath('/')).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });

  it.each(['javascript:alert(1)', 'data:text/html,unsafe'])(
    'does not redirect to an unsafe protocol: %s',
    homeUrl => {
      const replace = jest.fn();
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: {
          href: 'https://app.example.com/',
          pathname: '/',
          replace,
        },
      });

      expect(redirectToHomeUrlIfRootPath(homeUrl)).toBe(false);
      expect(replace).not.toHaveBeenCalled();
    },
  );

  it('does not override an explicit course path', () => {
    const replace = jest.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        href: 'https://app.example.com/c/course-2',
        pathname: '/c/course-2',
        replace,
      },
    });

    expect(redirectToHomeUrlIfRootPath('/c/course-1')).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });

  it('does not redirect a non-entry path', () => {
    const replace = jest.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        href: 'https://app.example.com/admin',
        pathname: '/admin',
        replace,
      },
    });

    expect(redirectToHomeUrlIfRootPath('/admin')).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });
});
