import { waitFor } from '@testing-library/react';

const paymentSettings = (owner: string) => ({
  billingEnabled: 'true',
  stripeEnabled: 'true',
  stripePublishableKey: `pk_${owner}`,
  paymentChannels: ['stripe'],
});
const disabledPaymentSettings = {
  billingEnabled: 'false',
  stripeEnabled: 'false',
  stripePublishableKey: '',
  paymentChannels: [],
};
const runtimeResponse = (owner: string) => ({
  ok: true,
  json: async () => ({
    code: 0,
    data: {
      logoWideUrl: `/${owner}.png`,
      logoSquareUrl: `/${owner}-square.png`,
      billingEnabled: true,
      stripeEnabled: true,
      stripePublishableKey: `pk_${owner}`,
      paymentChannels: ['stripe'],
    },
  }),
});
const failedResponse = { ok: false, status: 503 };
const discoveryResponse = {
  ok: true,
  json: async () => ({ apiBaseUrl: '' }),
};
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => {
    resolve = done;
  });
  return { promise, resolve };
};

describe('runtime payment context isolation', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  test.each(['/c/b', '/admin/operations/billing'])(
    'clears the previous merchant while %s loads and remains closed after failure',
    async pathname => {
      const waiting = deferred<typeof failedResponse>();
      let retry = false;
      global.fetch = jest.fn(async (url: string) => {
        if (url === '/api/config') return discoveryResponse;
        if (url.includes('shifu_bid=a')) return runtimeResponse('a');
        return retry ? runtimeResponse('target') : waiting.promise;
      }) as jest.Mock;
      jest.spyOn(console, 'error').mockImplementation(() => undefined);

      await jest.isolateModulesAsync(async () => {
        const { useEnvStore } = await import('@/store/env-store');
        const { initializeEnvData } =
          await import('./initialize-runtime-config');
        await initializeEnvData('/c/a');
        expect(useEnvStore.getState()).toMatchObject(paymentSettings('a'));

        const loading = initializeEnvData(pathname);
        expect(useEnvStore.getState()).toMatchObject(disabledPaymentSettings);
        waiting.resolve(failedResponse);
        await loading;
        expect(useEnvStore.getState()).toMatchObject({
          ...disabledPaymentSettings,
          runtimeConfigLoaded: true,
          runtimeConfigContext: {
            courseId: pathname.startsWith('/c/') ? 'b' : '',
            status: 'failed',
          },
        });

        retry = true;
        await initializeEnvData(pathname);
        expect(useEnvStore.getState()).toMatchObject(paymentSettings('target'));
      });
    },
  );

  test('keeps successive failed contexts closed after losing the previous loaded key', async () => {
    global.fetch = jest.fn(async (url: string) => {
      if (url === '/api/config') return discoveryResponse;
      return url.includes('shifu_bid=a')
        ? runtimeResponse('a')
        : failedResponse;
    }) as jest.Mock;
    jest.spyOn(console, 'error').mockImplementation(() => undefined);

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      await initializeEnvData('/c/a');
      await initializeEnvData('/c/b');
      await initializeEnvData('/c/c');
      expect(useEnvStore.getState()).toMatchObject({
        ...disabledPaymentSettings,
        runtimeConfigContext: { courseId: 'c', status: 'failed' },
      });
    });
  });

  test('does not trust unowned bootstrap merchant defaults when the first course fails', async () => {
    global.fetch = jest.fn(async (url: string) =>
      url === '/api/config' ? discoveryResponse : failedResponse,
    ) as jest.Mock;
    jest.spyOn(console, 'error').mockImplementation(() => undefined);

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      useEnvStore.setState(paymentSettings('bootstrap'));
      await initializeEnvData('/c/a');
      expect(useEnvStore.getState()).toMatchObject(disabledPaymentSettings);
      expect(useEnvStore.getState().baseURL).toBe('');
    });
  });

  test('a stale failure cannot clear a newer successful merchant context', async () => {
    const waiting = deferred<typeof failedResponse>();
    global.fetch = jest.fn(async (url: string) => {
      if (url === '/api/config') return discoveryResponse;
      if (url.includes('shifu_bid=b')) return waiting.promise;
      return runtimeResponse(url.includes('shifu_bid=c') ? 'c' : 'a');
    }) as jest.Mock;

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      await initializeEnvData('/c/a');
      const loadingB = initializeEnvData('/c/b');
      await waitFor(() =>
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/runtime-config?shifu_bid=b',
          { cache: 'no-store' },
        ),
      );
      await initializeEnvData('/c/c');
      waiting.resolve(failedResponse);
      await loadingB;
      expect(useEnvStore.getState()).toMatchObject({
        ...paymentSettings('c'),
        runtimeConfigContext: { courseId: 'c', status: 'ready' },
      });
    });
  });

  test('preserves verified settings when refreshing the same course fails', async () => {
    global.fetch = jest.fn(async (url: string) =>
      url === '/api/config' ? discoveryResponse : failedResponse,
    ) as jest.Mock;
    jest.spyOn(console, 'error').mockImplementation(() => undefined);

    await jest.isolateModulesAsync(async () => {
      const { useEnvStore } = await import('@/store/env-store');
      const { initializeEnvData } = await import('./initialize-runtime-config');
      useEnvStore.setState({
        ...paymentSettings('a'),
        runtimeConfigLoaded: true,
        runtimeConfigContext: {
          courseId: 'a',
          status: 'ready',
          generation: 12,
        },
      });
      await initializeEnvData('/c/a');
      expect(useEnvStore.getState()).toMatchObject(paymentSettings('a'));
      await initializeEnvData('/c/a');
      expect(useEnvStore.getState()).toMatchObject(paymentSettings('a'));
    });
  });
});
