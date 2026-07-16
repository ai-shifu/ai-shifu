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
