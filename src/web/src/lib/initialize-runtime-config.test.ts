describe('runtime host branding', () => {
  const originalFetch = global.fetch;
  const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const originalLocation = {
    href: window.location.href,
    origin: window.location.origin,
    host: window.location.host,
    hostname: window.location.hostname,
    pathname: window.location.pathname,
  };

  afterEach(() => {
    global.fetch = originalFetch;
    Object.assign(window.location, originalLocation);
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

        expect(useEnvStore.getState().logoWideUrl).toBe('/site-wide.png');
      });
    },
  );

  test.each([
    [
      'http://localhost:3000',
      'http://localhost:8080/api///',
      'http://localhost:8080/api',
    ],
    [
      'https://official.frontend.test',
      'https://explicit.backend.test/api///',
      'https://explicit.backend.test/api',
    ],
  ])(
    'respects explicit discovery for %s',
    async (origin, configured, expectedBase) => {
      Object.assign(window.location, {
        origin,
        host: new URL(origin).host,
        pathname: '/admin',
      });
      global.fetch = jest
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ apiBaseUrl: configured }),
        })
        .mockResolvedValue({
          ok: true,
          json: async () => ({ data: {} }),
        });

      await jest.isolateModulesAsync(async () => {
        const { useEnvStore } = await import('@/store/env-store');
        const { initializeEnvData } =
          await import('./initialize-runtime-config');

        await initializeEnvData();

        expect(global.fetch).toHaveBeenCalledWith(
          `${expectedBase}/runtime-config`,
          { cache: 'no-store' },
        );
        expect(useEnvStore.getState().baseURL).toBe(expectedBase);
      });
    },
  );

  test.each(
    ['http', 'json', 'network', 'response-shape'].flatMap(failure => [
      {
        failure,
        origin: 'https://backend.example.test',
        configured: 'https://backend.example.test/backend///',
        expectedBase: 'https://backend.example.test/backend',
        runtimeUrl:
          'https://backend.example.test/backend/api/runtime-config?shifu_bid=course-1',
      },
      {
        failure,
        origin: 'http://localhost:3000',
        configured: 'http://localhost:8080/api///',
        expectedBase: 'http://localhost:8080/api',
        runtimeUrl:
          'http://localhost:8080/api/runtime-config?shifu_bid=course-1',
      },
      {
        failure,
        origin: 'https://creator.example.test',
        configured: 'https://app.example.test/backend///',
        expectedBase: '',
        runtimeUrl: '/api/runtime-config?shifu_bid=course-1',
      },
      {
        failure,
        origin: 'https://academy.customer.test',
        configured: 'https://app.example.test/backend///',
        expectedBase: '',
        runtimeUrl: '/api/runtime-config?shifu_bid=course-1',
      },
    ]),
  )(
    'loads runtime settings on $origin after $failure discovery failure',
    async ({ failure, origin, configured, expectedBase, runtimeUrl }) => {
      process.env.NEXT_PUBLIC_API_BASE_URL = configured;
      Object.assign(window.location, {
        href: `${origin}/c/course-1`,
        origin,
        host: new URL(origin).host,
        hostname: new URL(origin).hostname,
        pathname: '/c/course-1',
      });
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
        expect(global.fetch).toHaveBeenNthCalledWith(2, runtimeUrl, {
          cache: 'no-store',
        });
        expect(useEnvStore.getState()).toEqual(
          expect.objectContaining({
            baseURL: expectedBase,
            logoWideUrl: '/backend-logo.png',
            appId: 'backend-wechat-app',
            paymentChannels: ['stripe'],
            runtimeConfigLoaded: true,
          }),
        );
        expect(getCachedDynamicApiBaseUrl()).toBe(expectedBase);
        expect(getResolvedBaseURL()).toBe(expectedBase || origin);
        await expect(getDynamicApiBaseUrl()).resolves.toBe(expectedBase);
        expect(global.fetch).toHaveBeenCalledTimes(2);
      });
    },
  );
});
