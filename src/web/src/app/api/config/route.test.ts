import {
  resolveApiBaseUrlForHost,
  shouldUseSameOriginApiBase,
} from './route-utils';

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

  it.each([
    [
      'https://app.example.com/backend',
      'app.example.com',
      'https://app.example.com/backend',
    ],
    ['http://localhost:8080', 'localhost:3000', 'http://localhost:8080'],
    ['https://app.example.com', 'creator.example.com', ''],
    ['https://app.example.com', 'academy.customer.com', ''],
    [
      'https://app.example.com',
      'APP.EXAMPLE.COM, proxy.internal',
      'https://app.example.com',
    ],
    ['/backend', 'academy.customer.com', '/backend'],
  ])('resolves %s for request host %s', (configured, host, expected) => {
    expect(resolveApiBaseUrlForHost(configured, host)).toBe(expected);
  });
});
