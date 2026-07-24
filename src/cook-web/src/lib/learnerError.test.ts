import { resolveLearnerErrorMessage } from './learnerError';
import { getRequestFallbackMessage } from './request';

jest.mock('i18next', () => ({
  t: (key: string) => `i18n:${key}`,
}));

jest.mock('./request', () => ({
  getRequestFallbackMessage: jest.fn(() => 'request-fallback'),
}));

describe('resolveLearnerErrorMessage', () => {
  afterEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(window.navigator, 'onLine', {
      configurable: true,
      value: true,
    });
  });

  it('prefers explicit learner-facing messages', () => {
    expect(
      resolveLearnerErrorMessage({
        message: '  backend message  ',
        fallbackMessage: 'i18n:module.chat.requestFailed',
      }),
    ).toBe('backend message');
    expect(getRequestFallbackMessage).not.toHaveBeenCalled();
  });

  it('uses shared request fallback for HTTP-style failures', () => {
    expect(
      resolveLearnerErrorMessage({
        error: { status: 503 },
        fallbackMessage: 'i18n:module.preview.requestFailed',
      }),
    ).toBe('request-fallback');
    expect(getRequestFallbackMessage).toHaveBeenCalledWith({ status: 503 });
  });

  it('uses shared request fallback when the browser is offline', () => {
    Object.defineProperty(window.navigator, 'onLine', {
      configurable: true,
      value: false,
    });

    expect(
      resolveLearnerErrorMessage({
        fallbackMessage: 'i18n:module.preview.requestFailed',
      }),
    ).toBe('request-fallback');
    expect(getRequestFallbackMessage).toHaveBeenCalledWith(undefined);
  });

  it('falls back to the learner-context i18n copy when no request context exists', () => {
    expect(
      resolveLearnerErrorMessage({
        fallbackMessage: 'i18n:module.chat.requestFailed',
      }),
    ).toBe('i18n:module.chat.requestFailed');
    expect(getRequestFallbackMessage).not.toHaveBeenCalled();
  });
});
