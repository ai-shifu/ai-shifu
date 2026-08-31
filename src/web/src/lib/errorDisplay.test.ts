import {
  resolveErrorDisplayMessage,
  shouldHideErrorDisplayMessage,
} from './errorDisplay';

describe('errorDisplay helpers', () => {
  test('prefers explicit error messages for non-protected errors', () => {
    expect(
      resolveErrorDisplayMessage({
        errorCode: 500,
        errorMessage: 'Preview stream timed out',
        fallbackMessage: 'Server error',
      }),
    ).toBe('Preview stream timed out');
  });

  test('falls back when explicit error messages are disabled', () => {
    expect(
      resolveErrorDisplayMessage({
        errorCode: 500,
        errorMessage: 'Preview stream timed out',
        fallbackMessage: 'Server error',
        showDetails: false,
      }),
    ).toBe('Server error');
  });

  test('hides explicit messages for protected permission and auth errors', () => {
    expect(shouldHideErrorDisplayMessage(401)).toBe(true);
    expect(
      resolveErrorDisplayMessage({
        errorCode: 401,
        errorMessage: 'Missing teacher permission',
        fallbackMessage: 'No permission',
      }),
    ).toBe('No permission');
    expect(
      resolveErrorDisplayMessage({
        errorCode: 1001,
        errorMessage: 'Session expired',
        fallbackMessage: 'Please sign in again',
      }),
    ).toBe('Please sign in again');
  });
});
