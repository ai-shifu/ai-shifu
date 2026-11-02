import { waitFor } from '@testing-library/react';

const runtimeResponse = (data: Record<string, unknown>) => ({
  ok: true,
  json: async () => ({
    code: 0,
    data: { logoWideUrl: '', logoSquareUrl: '', ...data },
  }),
});

const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(accept => {
    resolve = accept;
  });
  return { promise, resolve };
};

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
          json: async () => ({ data: { logoWideUrl: '', logoSquareUrl: '' } }),
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
              logoSquareUrl: '/backend-square.png',
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

  test('refreshes course settings and restores platform logos when leaving a course', async () => {
    const platform = {
      logoWideUrl: '/platform-wide.png',
      logoSquareUrl: '/platform-square.png',
      faviconUrl: '/platform.ico',
      homeUrl: '/admin',
      contactUsUrl: '/contact',
      stripePublishableKey: 'pk_platform',
    };
    const a = {
      ...platform,
      logoWideUrl: '/a.png',
      stripePublishableKey: 'pk_a',
    };
    const b = {
      ...platform,
      logoWideUrl: '/b.png',
      stripePublishableKey: 'pk_b',
    };
    global.fetch = jest.fn(async (url: string) => {
      if (url === '/api/config')
        return { ok: true, json: async () => ({ apiBaseUrl: '' }) };
      return runtimeResponse(
        url.includes('shifu_bid=a')
          ? a
          : url.includes('shifu_bid=b')
            ? b
            : platform,
      );
    }) as jest.Mock;

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      await initializeEnvData('/admin');
      await initializeEnvData('/c/a');
      expect(useEnvStore.getState().logoWideUrl).toBe('/a.png');

      const requests = jest.mocked(global.fetch).mock.calls.length;
      await Promise.all([
        initializeEnvData('/c/a/lesson-2'),
        initializeEnvData('/c/a'),
      ]);
      expect(global.fetch).toHaveBeenCalledTimes(requests);

      const states: Array<{ logo: string; key: string; loaded: boolean }> = [];
      const unsubscribe = useEnvStore.subscribe(state =>
        states.push({
          logo: state.logoWideUrl,
          key: state.stripePublishableKey,
          loaded: state.runtimeConfigLoaded,
        }),
      );
      await initializeEnvData('/c/b');
      expect(useEnvStore.getState()).toMatchObject({
        logoWideUrl: '/b.png',
        stripePublishableKey: 'pk_b',
        faviconUrl: '/platform.ico',
        homeUrl: '/admin',
        contactUsUrl: '/contact',
      });
      expect(
        states
          .filter(state => state.logo === '/b.png')
          .every(state => state.key === 'pk_b'),
      ).toBe(true);
      expect(states.every(state => state.loaded)).toBe(true);

      const returning = initializeEnvData('/admin/orders');
      expect(useEnvStore.getState().logoWideUrl).toBe('/platform-wide.png');
      await returning;
      expect(useEnvStore.getState().stripePublishableKey).toBe('pk_platform');
      unsubscribe();
    });
  });

  test('a stale course response cannot overwrite a newer course or release its startup gate', async () => {
    const a = deferred<ReturnType<typeof runtimeResponse>>();
    const b = deferred<ReturnType<typeof runtimeResponse>>();
    global.fetch = jest.fn(async (url: string) => {
      if (url === '/api/config')
        return { ok: true, json: async () => ({ apiBaseUrl: '' }) };
      return url.includes('shifu_bid=a') ? a.promise : b.promise;
    }) as jest.Mock;

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      const loadingA = initializeEnvData('/c/a');
      await waitFor(() =>
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/runtime-config?shifu_bid=a',
          { cache: 'no-store' },
        ),
      );
      const loadingB = initializeEnvData('/c/b');
      const contextB = useEnvStore.getState().runtimeConfigContext;
      expect(contextB).toMatchObject({ courseId: 'b', status: 'loading' });
      a.resolve(
        runtimeResponse({
          logoWideUrl: '/a.png',
          stripePublishableKey: 'pk_a',
        }),
      );
      await loadingA;
      expect(useEnvStore.getState().runtimeConfigLoaded).toBe(false);
      expect(useEnvStore.getState().runtimeConfigContext).toEqual(contextB);
      expect(useEnvStore.getState().logoWideUrl).not.toBe('/a.png');

      b.resolve(
        runtimeResponse({
          logoWideUrl: '/b.png',
          stripePublishableKey: 'pk_b',
        }),
      );
      await loadingB;
      expect(useEnvStore.getState()).toMatchObject({
        logoWideUrl: '/b.png',
        stripePublishableKey: 'pk_b',
        runtimeConfigLoaded: true,
        runtimeConfigContext: { ...contextB, status: 'ready' },
      });
    });
  });

  test('reuses an in-flight course request when returning to it from another course', async () => {
    const a = deferred<ReturnType<typeof runtimeResponse>>();
    const b = deferred<ReturnType<typeof runtimeResponse>>();
    global.fetch = jest.fn(async (url: string) => {
      if (url === '/api/config')
        return { ok: true, json: async () => ({ apiBaseUrl: '' }) };
      return url.includes('shifu_bid=a') ? a.promise : b.promise;
    }) as jest.Mock;

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      const firstA = initializeEnvData('/c/a');
      const sameA = initializeEnvData('/c/a/lesson-2');
      await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
      const loadingB = initializeEnvData('/c/b');
      await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(3));
      const returningA = initializeEnvData('/c/a');
      expect(global.fetch).toHaveBeenCalledTimes(3);

      a.resolve(
        runtimeResponse({
          logoWideUrl: '/a.png',
          stripePublishableKey: 'pk_a',
        }),
      );
      await Promise.all([firstA, sameA, returningA]);
      expect(useEnvStore.getState().logoWideUrl).toBe('/a.png');
      b.resolve(
        runtimeResponse({
          logoWideUrl: '/b.png',
          stripePublishableKey: 'pk_b',
        }),
      );
      await loadingB;
      expect(useEnvStore.getState()).toMatchObject({
        logoWideUrl: '/a.png',
        stripePublishableKey: 'pk_a',
      });
    });
  });

  test('a slow course cannot overwrite the platform after navigation to admin', async () => {
    const a = deferred<ReturnType<typeof runtimeResponse>>();
    global.fetch = jest.fn(async (url: string) => {
      if (url === '/api/config')
        return { ok: true, json: async () => ({ apiBaseUrl: '' }) };
      if (url.includes('shifu_bid=a')) return a.promise;
      return runtimeResponse({
        logoWideUrl: '/platform.png',
        stripePublishableKey: 'pk_platform',
      });
    }) as jest.Mock;

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      const loadingA = initializeEnvData('/c/a');
      await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
      await initializeEnvData('/admin');
      a.resolve(
        runtimeResponse({
          logoWideUrl: '/a.png',
          stripePublishableKey: 'pk_a',
        }),
      );
      await loadingA;
      expect(useEnvStore.getState()).toMatchObject({
        logoWideUrl: '/platform.png',
        stripePublishableKey: 'pk_platform',
      });
    });
  });

  test('keeps a confirmed customer host logo while loading other courses or admin', async () => {
    const waiting = deferred<ReturnType<typeof runtimeResponse>>();
    const host = {
      logoWideUrl: '/customer.png',
      logoSquareUrl: '/customer-square.png',
      faviconUrl: '/customer.ico',
      homeUrl: '/customer-home',
      contactUsUrl: '/customer-contact',
      domain: { is_custom_domain: true },
    };
    global.fetch = jest.fn(async (url: string) => {
      if (url === '/api/config')
        return { ok: true, json: async () => ({ apiBaseUrl: '' }) };
      return url.includes('shifu_bid=b')
        ? waiting.promise
        : runtimeResponse(host);
    }) as jest.Mock;

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      await initializeEnvData('/c/a');
      const loadingB = initializeEnvData('/c/b');
      const presentation = {
        logoWideUrl: host.logoWideUrl,
        logoSquareUrl: host.logoSquareUrl,
        faviconUrl: host.faviconUrl,
        homeUrl: host.homeUrl,
        contactUsUrl: host.contactUsUrl,
      };
      expect(useEnvStore.getState()).toMatchObject(presentation);
      await initializeEnvData('/admin');
      waiting.resolve(runtimeResponse(host));
      await loadingB;
      expect(useEnvStore.getState()).toMatchObject(presentation);
    });
  });

  test.each(['http', 'json', 'business-error', 'discovery-only'])(
    'retries the same course after a %s runtime failure without clearing existing business settings',
    async failure => {
      Object.assign(window.location, {
        origin: 'https://creator.example.test',
        host: 'creator.example.test',
      });
      jest.spyOn(console, 'error').mockImplementation(() => undefined);
      global.fetch = jest
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ apiBaseUrl: '' }),
        })
        .mockResolvedValueOnce({
          ok: failure !== 'http',
          status: failure === 'http' ? 503 : 200,
          json: async () =>
            failure === 'json'
              ? JSON.parse('<html>Unavailable</html>')
              : failure === 'business-error'
                ? { code: 4004, message: 'Course unavailable' }
                : { apiBaseUrl: '' },
        })
        .mockResolvedValue(
          runtimeResponse({
            logoWideUrl: '/a.png',
            stripePublishableKey: 'pk_a',
          }),
        );

      await jest.isolateModulesAsync(async () => {
        const { useEnvStore } = await import('@/store/env-store');
        const { getResolvedBaseURL } = await import('./env-utils');
        const { initializeEnvData } =
          await import('./initialize-runtime-config');
        useEnvStore.setState({
          baseURL: 'https://platform-api.example.test',
          stripePublishableKey: 'existing-key',
        });
        await initializeEnvData('/c/a');
        expect(useEnvStore.getState()).toMatchObject({
          runtimeConfigLoaded: true,
          baseURL: '',
          stripePublishableKey: 'existing-key',
        });
        expect(getResolvedBaseURL()).toBe('https://creator.example.test');
        await initializeEnvData('/c/a');
        expect(useEnvStore.getState()).toMatchObject({
          logoWideUrl: '/a.png',
          stripePublishableKey: 'pk_a',
        });
        expect(global.fetch).toHaveBeenCalledTimes(3);
      });
    },
  );
});
