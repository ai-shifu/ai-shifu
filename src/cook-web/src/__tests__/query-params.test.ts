import { getQueryParams } from '../c-utils/urlUtils';

describe('getQueryParams', () => {
  it('parses query params with decoded values and strips hashes', () => {
    expect(
      getQueryParams(
        'https://example.com/c/123?mode=listen&name=AI%20Shifu#lesson',
      ),
    ).toEqual({
      mode: 'listen',
      name: 'AI Shifu',
    });
  });

  it('keeps valueless query params as empty strings', () => {
    expect(getQueryParams('https://example.com/c/123?debug&empty=')).toEqual({
      debug: '',
      empty: '',
    });
  });
});
