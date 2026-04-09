import UnifiedI18nBackend from './unified-i18n-backend';

describe('UnifiedI18nBackend', () => {
  const originalFetch = global.fetch;
  const originalWindow = global.window;

  const readNamespace = (
    backend: UnifiedI18nBackend,
    language: string,
    namespace: string,
  ) =>
    new Promise<Record<string, unknown>>((resolve, reject) => {
      backend.read(language, namespace, (error, loadedResources) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(loadedResources as Record<string, unknown>);
      });
    });

  afterEach(() => {
    jest.restoreAllMocks();
    global.fetch = originalFetch;
    Object.defineProperty(global, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });

  test('loads requested namespace even when it is missing from configured namespaces', async () => {
    const backend = new UnifiedI18nBackend();
    backend.init(null, {
      loadPath: '/api/i18n',
      namespaces: ['module.order'],
    });

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

    Object.defineProperty(global, 'window', {
      configurable: true,
      value: {
        location: {
          origin: 'http://localhost:3000',
        },
      },
    });

    const resources = await readNamespace(
      backend,
      'zh-CN',
      'module.operationsCourse',
    );

    const requestUrl = new URL(fetchMock.mock.calls[0][0] as string);

    expect(requestUrl.searchParams.get('ns')).toBe(
      'module.operationsCourse,module.order',
    );
    expect(resources).toEqual({
      title: 'Course',
    });
  });

  test('preserves previously loaded namespaces across incremental reads', async () => {
    const backend = new UnifiedI18nBackend();
    backend.init(null, {
      loadPath: '/api/i18n',
      namespaces: [],
    });

    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          translations: {
            'module.operationsCourse': {
              title: 'Course',
            },
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          translations: {
            'module.order': {
              title: 'Orders',
            },
          },
        }),
      } as Response);
    global.fetch = fetchMock as typeof fetch;

    Object.defineProperty(global, 'window', {
      configurable: true,
      value: {
        location: {
          origin: 'http://localhost:3000',
        },
      },
    });

    await readNamespace(backend, 'zh-CN', 'module.operationsCourse');
    await readNamespace(backend, 'zh-CN', 'module.order');
    const resources = await readNamespace(
      backend,
      'zh-CN',
      'module.operationsCourse',
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(resources).toEqual({
      title: 'Course',
    });
  });
});
