import { redirectToHomeUrlIfRootPath } from './utils';

const originalLocation = window.location;

describe('redirectToHomeUrlIfRootPath', () => {
  afterAll(() => {
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
});
