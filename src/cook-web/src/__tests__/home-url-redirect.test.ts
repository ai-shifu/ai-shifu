import { redirectToHomeUrlIfRootPath } from '../lib/utils';

describe('redirectToHomeUrlIfRootPath', () => {
  let replaceSpy: jest.SpyInstance;

  beforeEach(() => {
    window.history.replaceState({}, '', 'http://localhost/');
    replaceSpy = jest
      .spyOn(window.location, 'replace')
      .mockImplementation(() => undefined);
  });

  afterEach(() => {
    replaceSpy.mockRestore();
  });

  it('redirects root requests to the configured home url', () => {
    expect(redirectToHomeUrlIfRootPath('/admin')).toBe(true);
    expect(replaceSpy).toHaveBeenCalledWith('/admin');
  });

  it('does not redirect when the configured home url matches the current root location', () => {
    expect(redirectToHomeUrlIfRootPath('/')).toBe(false);
    expect(replaceSpy).not.toHaveBeenCalled();
  });
});
