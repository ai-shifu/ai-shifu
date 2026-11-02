describe('runtime host branding', () => {
  const originalFetch = global.fetch;
  const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
    if (originalApiBaseUrl === undefined) {
      delete process.env.NEXT_PUBLIC_API_BASE_URL;
    } else {
      process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
    }
  });

  test.each([
    ['/admin', '/api/runtime-config'],
    ['/c/course-1', '/api/runtime-config?shifu_bid=course-1'],
  ])(
    'applies the server site brand on %s while preserving course business context',
    async (pathname, runtimeUrl) => {
      Object.assign(window.location, { pathname });
      global.fetch = jest
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ apiBaseUrl: '' }),
        })
        .mockResolvedValue({
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

        expect(global.fetch).toHaveBeenCalledTimes(2);
        expect(useEnvStore.getState().logoWideUrl).toBe('/site-wide.png');
      });
    },
  );

  test('keeps an explicitly configured backend origin for local development', async () => {
    Object.assign(window.location, { pathname: '/admin' });
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ apiBaseUrl: 'http://localhost:8080/api///' }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({ data: {} }),
      });

    await jest.isolateModulesAsync(async () => {
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

  test.each(['http', 'json', 'network', 'response-shape'])(
    'loads runtime settings from the configured backend after %s discovery failure',
    async failure => {
      process.env.NEXT_PUBLIC_API_BASE_URL = 'https://backend.example.test///';
      Object.assign(window.location, { pathname: '/c/course-1' });
      jest.spyOn(console, 'warn').mockImplementation(() => undefined);
      global.fetch = jest
        .fn()
        .mockImplementationOnce(async () => {
          if (failure === 'network') {
            throw new TypeError('Network request failed');
          }
          return {
            ok: failure !== 'http',
            status: failure === 'http' ? 503 : 200,
            json: async () =>
              failure === 'json' ? JSON.parse('<html>Unavailable</html>') : {},
          };
        })
        .mockResolvedValue({
          ok: true,
          json: async () => ({
            data: {
              logoWideUrl: '/backend-logo.png',
              wechatAppId: 'backend-wechat-app',
              paymentChannels: ['stripe'],
            },
          }),
        });

      await jest.isolateModulesAsync(async () => {
        const { useEnvStore } = await import('@/store/env-store');
        const { getCachedDynamicApiBaseUrl, getDynamicApiBaseUrl } =
          await import('@/config/environment');
        const { getResolvedBaseURL } = await import('./env-utils');
        const { initializeEnvData } =
          await import('./initialize-runtime-config');

        await initializeEnvData();

        expect(global.fetch).toHaveBeenNthCalledWith(1, '/api/config');
        expect(global.fetch).toHaveBeenNthCalledWith(
          2,
          'https://backend.example.test/api/runtime-config?shifu_bid=course-1',
          { cache: 'no-store' },
        );
        expect(useEnvStore.getState()).toEqual(
          expect.objectContaining({
            baseURL: 'https://backend.example.test',
            logoWideUrl: '/backend-logo.png',
            appId: 'backend-wechat-app',
            paymentChannels: ['stripe'],
            runtimeConfigLoaded: true,
          }),
        );
        expect(getCachedDynamicApiBaseUrl()).toBe(
          'https://backend.example.test',
        );
        expect(getResolvedBaseURL()).toBe('https://backend.example.test');
        await expect(getDynamicApiBaseUrl()).resolves.toBe(
          'https://backend.example.test',
        );
        expect(global.fetch).toHaveBeenCalledTimes(2);
      });
    },
  );
});
