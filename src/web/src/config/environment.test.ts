describe('frontend build metadata', () => {
  const originalBuildEnvironment = {
    NEXT_PUBLIC_APP_VERSION: process.env.NEXT_PUBLIC_APP_VERSION,
    NEXT_PUBLIC_APP_BUILD_SHA: process.env.NEXT_PUBLIC_APP_BUILD_SHA,
  };

  afterEach(() => {
    for (const [key, value] of Object.entries(originalBuildEnvironment)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  });

  it('exposes the bundled release and full commit without runtime configuration', async () => {
    process.env.NEXT_PUBLIC_APP_VERSION = '9.8.7';
    process.env.NEXT_PUBLIC_APP_BUILD_SHA = 'a'.repeat(40);

    await jest.isolateModulesAsync(async () => {
      const { environment } = await import('./environment');

      expect(environment.appVersion).toBe('9.8.7');
      expect(environment.appBuildSha).toBe('a'.repeat(40));

      process.env.NEXT_PUBLIC_APP_VERSION = '1.0.0';
      process.env.NEXT_PUBLIC_APP_BUILD_SHA = 'b'.repeat(40);

      expect(environment.appVersion).toBe('9.8.7');
      expect(environment.appBuildSha).toBe('a'.repeat(40));
    });
  });

  it('does not invent unavailable build metadata', async () => {
    delete process.env.NEXT_PUBLIC_APP_VERSION;
    delete process.env.NEXT_PUBLIC_APP_BUILD_SHA;

    await jest.isolateModulesAsync(async () => {
      const { environment } = await import('./environment');

      expect(environment.appVersion).toBe('');
      expect(environment.appBuildSha).toBe('');
    });
  });
});

describe('cached runtime API base URL', () => {
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

  it.each(['http', 'json', 'network', 'response-shape'])(
    'caches the configured backend after a %s discovery failure',
    async failure => {
      process.env.NEXT_PUBLIC_API_BASE_URL = 'https://backend.example.test///';
      jest.spyOn(console, 'warn').mockImplementation(() => undefined);
      global.fetch = jest.fn(async () => {
        if (failure === 'network') {
          throw new TypeError('Network request failed');
        }
        return {
          ok: failure !== 'http',
          status: failure === 'http' ? 503 : 200,
          json: async () =>
            failure === 'json' ? JSON.parse('<html>Unavailable</html>') : {},
        } as Response;
      });

      await jest.isolateModulesAsync(async () => {
        const { getCachedDynamicApiBaseUrl, getDynamicApiBaseUrl } =
          await import('./environment');

        expect(getCachedDynamicApiBaseUrl()).toBeUndefined();
        await expect(getDynamicApiBaseUrl()).resolves.toBe(
          'https://backend.example.test',
        );
        expect(getCachedDynamicApiBaseUrl()).toBe(
          'https://backend.example.test',
        );
        await expect(getDynamicApiBaseUrl()).resolves.toBe(
          'https://backend.example.test',
        );
        expect(global.fetch).toHaveBeenCalledTimes(1);
      });
    },
  );
});

describe('Spanish legal document URLs', () => {
  const originalAgreementUrl = process.env.LEGAL_AGREEMENT_URL_ES_ES;
  const originalPrivacyUrl = process.env.LEGAL_PRIVACY_URL_ES_ES;

  afterEach(() => {
    if (originalAgreementUrl === undefined) {
      delete process.env.LEGAL_AGREEMENT_URL_ES_ES;
    } else {
      process.env.LEGAL_AGREEMENT_URL_ES_ES = originalAgreementUrl;
    }
    if (originalPrivacyUrl === undefined) {
      delete process.env.LEGAL_PRIVACY_URL_ES_ES;
    } else {
      process.env.LEGAL_PRIVACY_URL_ES_ES = originalPrivacyUrl;
    }
  });

  it('exposes configured es-ES agreement and privacy URLs', async () => {
    process.env.LEGAL_AGREEMENT_URL_ES_ES = 'https://example.test/acuerdo';
    process.env.LEGAL_PRIVACY_URL_ES_ES = 'https://example.test/privacidad';

    await jest.isolateModulesAsync(async () => {
      const { environment } = await import('./environment');

      expect(environment.legalUrls.agreement['es-ES']).toBe(
        'https://example.test/acuerdo',
      );
      expect(environment.legalUrls.privacy['es-ES']).toBe(
        'https://example.test/privacidad',
      );
    });
  });
});

describe('German legal document URLs', () => {
  const originalAgreementUrl = process.env.LEGAL_AGREEMENT_URL_DE_DE;
  const originalPrivacyUrl = process.env.LEGAL_PRIVACY_URL_DE_DE;

  afterEach(() => {
    if (originalAgreementUrl === undefined) {
      delete process.env.LEGAL_AGREEMENT_URL_DE_DE;
    } else {
      process.env.LEGAL_AGREEMENT_URL_DE_DE = originalAgreementUrl;
    }
    if (originalPrivacyUrl === undefined) {
      delete process.env.LEGAL_PRIVACY_URL_DE_DE;
    } else {
      process.env.LEGAL_PRIVACY_URL_DE_DE = originalPrivacyUrl;
    }
  });

  it('exposes configured de-DE agreement and privacy URLs', async () => {
    process.env.LEGAL_AGREEMENT_URL_DE_DE = 'https://example.test/vereinbarung';
    process.env.LEGAL_PRIVACY_URL_DE_DE = 'https://example.test/datenschutz';

    await jest.isolateModulesAsync(async () => {
      const { environment } = await import('./environment');

      expect(environment.legalUrls.agreement['de-DE']).toBe(
        'https://example.test/vereinbarung',
      );
      expect(environment.legalUrls.privacy['de-DE']).toBe(
        'https://example.test/datenschutz',
      );
    });
  });
});

describe('Urdu legal document URLs', () => {
  const originalAgreementUrl = process.env.LEGAL_AGREEMENT_URL_UR_PK;
  const originalPrivacyUrl = process.env.LEGAL_PRIVACY_URL_UR_PK;

  afterEach(() => {
    if (originalAgreementUrl === undefined) {
      delete process.env.LEGAL_AGREEMENT_URL_UR_PK;
    } else {
      process.env.LEGAL_AGREEMENT_URL_UR_PK = originalAgreementUrl;
    }
    if (originalPrivacyUrl === undefined) {
      delete process.env.LEGAL_PRIVACY_URL_UR_PK;
    } else {
      process.env.LEGAL_PRIVACY_URL_UR_PK = originalPrivacyUrl;
    }
  });

  it('exposes configured ur-PK agreement and privacy URLs', async () => {
    process.env.LEGAL_AGREEMENT_URL_UR_PK =
      'https://example.test/urdu-agreement';
    process.env.LEGAL_PRIVACY_URL_UR_PK = 'https://example.test/urdu-privacy';

    await jest.isolateModulesAsync(async () => {
      const { environment } = await import('./environment');

      expect(environment.legalUrls.agreement['ur-PK']).toBe(
        'https://example.test/urdu-agreement',
      );
      expect(environment.legalUrls.privacy['ur-PK']).toBe(
        'https://example.test/urdu-privacy',
      );
    });
  });
});
