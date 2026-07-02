import { redirectToHomeUrlIfRootPath } from './utils';

const setLocation = (href: string) => {
  const url = new URL(href);

  window.location.href = url.toString();
  window.location.pathname = url.pathname;
  window.location.search = url.search;
  window.location.hash = url.hash;
  window.location.origin = url.origin;
  window.location.protocol = url.protocol;
  window.location.host = url.host;
  window.location.hostname = url.hostname;
  window.location.port = url.port;
};

describe('redirectToHomeUrlIfRootPath', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setLocation('http://localhost:3000/');
  });

  it('does not redirect when the root home URL resolves to the current URL', () => {
    expect(redirectToHomeUrlIfRootPath('/')).toBe(false);
    expect(window.location.replace).not.toHaveBeenCalled();
  });

  it('redirects the root page to a configured course page', () => {
    expect(redirectToHomeUrlIfRootPath('/c/course-1')).toBe(true);
    expect(window.location.replace).toHaveBeenCalledWith('/c/course-1');
  });

  it('does not redirect a concrete course page', () => {
    setLocation('http://localhost:3000/c/course-1');

    expect(redirectToHomeUrlIfRootPath('/c/course-2')).toBe(false);
    expect(window.location.replace).not.toHaveBeenCalled();
  });

  it('does not redirect when /c resolves to /c/', () => {
    setLocation('http://localhost:3000/c/');

    expect(redirectToHomeUrlIfRootPath('/c')).toBe(false);
    expect(window.location.replace).not.toHaveBeenCalled();
  });
});
