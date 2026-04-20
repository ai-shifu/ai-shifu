import { buildLoginRedirectPath } from '../c-utils/urlUtils';

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
