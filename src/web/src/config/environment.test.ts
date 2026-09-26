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
