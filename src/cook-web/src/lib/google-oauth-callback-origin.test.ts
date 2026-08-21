import { resolveGoogleCallbackOrigin } from './google-oauth-callback-origin';

const mockCallbackOrigin = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    googleOauthCallbackOrigin: (...args: unknown[]) =>
      mockCallbackOrigin(...args),
  },
}));

describe('resolveGoogleCallbackOrigin', () => {
  beforeEach(() => {
    mockCallbackOrigin.mockReset();
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('returns the origin the backend validated', async () => {
    mockCallbackOrigin.mockResolvedValue({
      code: 0,
      data: { origin: 'https://learn.customer.example' },
    });

    await expect(resolveGoogleCallbackOrigin('state-1')).resolves.toBe(
      'https://learn.customer.example',
    );
  });

  it('accepts an unwrapped payload', async () => {
    mockCallbackOrigin.mockResolvedValue({
      origin: 'https://learn.customer.example',
    });

    await expect(resolveGoogleCallbackOrigin('state-1')).resolves.toBe(
      'https://learn.customer.example',
    );
  });

  it('returns empty when the backend refuses the origin', async () => {
    mockCallbackOrigin.mockResolvedValue({ code: 0, data: { origin: '' } });

    await expect(resolveGoogleCallbackOrigin('state-1')).resolves.toBe('');
  });

  it('never blocks the login when the lookup fails', async () => {
    mockCallbackOrigin.mockRejectedValue(new Error('network down'));

    await expect(resolveGoogleCallbackOrigin('state-1')).resolves.toBe('');
  });

  it('never blocks the login when the lookup hangs', async () => {
    jest.useFakeTimers();
    mockCallbackOrigin.mockReturnValue(new Promise(() => {}));

    const pending = resolveGoogleCallbackOrigin('state-1');
    jest.advanceTimersByTime(5000);

    await expect(pending).resolves.toBe('');
  });
});
