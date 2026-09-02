import { shouldUseSameOriginApiBase } from './route-utils';

describe('api config route host matching', () => {
  it('keeps the configured API base for localhost dev ports', () => {
    expect(shouldUseSameOriginApiBase('localhost:8080', 'localhost:3000')).toBe(
      false,
    );
    expect(shouldUseSameOriginApiBase('127.0.0.1:8080', '127.0.0.1:3000')).toBe(
      false,
    );
    expect(shouldUseSameOriginApiBase('0.0.0.0:8080', '0.0.0.0:3000')).toBe(
      false,
    );
    expect(shouldUseSameOriginApiBase('[::1]:8080', '[::1]:3000')).toBe(false);
  });

  it('uses same-origin API base when a custom host differs', () => {
    expect(
      shouldUseSameOriginApiBase('app.example.com', 'creator.example.com'),
    ).toBe(true);
  });

  it('keeps the configured API base on the configured host', () => {
    expect(
      shouldUseSameOriginApiBase('app.example.com', 'app.example.com'),
    ).toBe(false);
  });
});
