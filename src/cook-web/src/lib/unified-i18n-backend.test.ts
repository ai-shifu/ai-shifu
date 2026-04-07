import UnifiedI18nBackend from './unified-i18n-backend';

describe('UnifiedI18nBackend', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('loads requested namespace even when it is missing from configured namespaces', async () => {
    const backend = new UnifiedI18nBackend();
    backend.init(null, {
      loadPath: '/api/i18n',
      namespaces: ['module.order'],
    });

    const originalFetch = global.fetch;
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        translations: {
          'module.order': {
            title: 'Orders',
          },
          'module.operationsCourse': {
            title: 'Course',
          },
        },
      }),
    } as Response);
    global.fetch = fetchMock as typeof fetch;

    const originalWindow = global.window;
    Object.defineProperty(global, 'window', {
      configurable: true,
      value: {
        location: {
          origin: 'http://localhost:3000',
        },
      },
    });

    const resources = await new Promise<Record<string, unknown>>(
      (resolve, reject) => {
        backend.read(
          'zh-CN',
          'module.operationsCourse',
          (error, loadedResources) => {
            if (error) {
              reject(error);
              return;
            }
            resolve(loadedResources as Record<string, unknown>);
          },
        );
      },
    );

    const requestUrl = new URL(fetchMock.mock.calls[0][0] as string);

    expect(requestUrl.searchParams.get('ns')).toBe(
      'module.operationsCourse,module.order',
    );
    expect(resources).toEqual({
      title: 'Course',
    });

    global.fetch = originalFetch;
    Object.defineProperty(global, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });
});
