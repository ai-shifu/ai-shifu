jest.mock('@/config/environment', () => ({
  ...jest.requireActual('@/config/environment'),
  getDynamicApiBaseUrl: jest.fn().mockResolvedValue(''),
}));

jest.mock('@/lib/env-utils', () => ({ getBoolEnv: () => false }));

describe('runtime host branding', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  test.each([
    ['/admin', '/api/runtime-config'],
    ['/c/course-1', '/api/runtime-config?shifu_bid=course-1'],
  ])(
    'applies the server site brand on %s while preserving course business context',
    async (pathname, runtimeUrl) => {
      Object.assign(window.location, { pathname });
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          data: {
            logoWideUrl: '/site-wide.png',
            logoSquareUrl: '/site-square.png',
            faviconUrl: '/site-favicon.ico',
            homeUrl: 'https://site.example.test/home',
            stripePublishableKey: 'pk_course_owner',
            paymentChannels: ['stripe'],
          },
        }),
      });

      await jest.isolateModulesAsync(async () => {
        const { useEnvStore } = await import('@/store/env-store');
        const { initializeEnvData } =
          await import('./initialize-runtime-config');
        useEnvStore.setState({ baseURL: 'https://platform-api.example.test' });

        await initializeEnvData();

        expect(global.fetch).toHaveBeenCalledWith(runtimeUrl, {
          cache: 'no-store',
        });
        expect(useEnvStore.getState()).toEqual(
          expect.objectContaining({
            baseURL: '',
            logoWideUrl: '/site-wide.png',
            logoSquareUrl: '/site-square.png',
            faviconUrl: '/site-favicon.ico',
            homeUrl: 'https://site.example.test/home',
            stripePublishableKey: 'pk_course_owner',
            paymentChannels: ['stripe'],
            runtimeConfigLoaded: true,
          }),
        );

        Object.assign(window.location, {
          pathname: pathname === '/admin' ? '/c/other-course' : '/admin',
        });
        await initializeEnvData();

        expect(global.fetch).toHaveBeenCalledTimes(1);
        expect(useEnvStore.getState().logoWideUrl).toBe('/site-wide.png');
      });
    },
  );

  test('keeps an explicitly configured backend origin for local development', async () => {
    Object.assign(window.location, { pathname: '/admin' });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: {} }),
    });

    await jest.isolateModulesAsync(async () => {
      const { getDynamicApiBaseUrl } = await import('@/config/environment');
      jest
        .mocked(getDynamicApiBaseUrl)
        .mockResolvedValue('http://localhost:8080/api///');
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');

      await initializeEnvData();

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8080/api/runtime-config',
        { cache: 'no-store' },
      );
      expect(useEnvStore.getState().baseURL).toBe('http://localhost:8080/api');
    });
  });
});
