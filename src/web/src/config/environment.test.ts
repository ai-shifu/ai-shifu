describe('cached runtime API base URL', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it.each([
    ['https://api.example.test///', 'https://api.example.test'],
    ['', ''],
  ])(
    'exposes %s only after configuration resolves',
    async (configured, expected) => {
      await jest.isolateModulesAsync(async () => {
        const { getCachedDynamicApiBaseUrl, getDynamicApiBaseUrl } =
          await import('./environment');
        let resolveConfig!: (value: { apiBaseUrl: string }) => void;
        global.fetch = jest.fn().mockResolvedValue({
          ok: true,
          json: () =>
            new Promise(resolve => {
              resolveConfig = resolve;
            }),
        });

        expect(getCachedDynamicApiBaseUrl()).toBeUndefined();
        expect(global.fetch).not.toHaveBeenCalled();
        const loading = getDynamicApiBaseUrl();
        await Promise.resolve();
        expect(getCachedDynamicApiBaseUrl()).toBeUndefined();
        resolveConfig({ apiBaseUrl: configured });

        await expect(loading).resolves.toBe(expected);
        expect(getCachedDynamicApiBaseUrl()).toBe(expected);
        await expect(getDynamicApiBaseUrl()).resolves.toBe(expected);
        expect(global.fetch).toHaveBeenCalledTimes(1);
        expect(global.fetch).toHaveBeenCalledWith('/api/config');
      });
    },
  );
});
