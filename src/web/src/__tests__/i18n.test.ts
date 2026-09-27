describe('i18n language normalization', () => {
  const originalEnv = process.env.NEXT_PUBLIC_I18N_META;

  afterEach(() => {
    process.env.NEXT_PUBLIC_I18N_META = originalEnv;
  });

  test('normalizeLanguage picks best match and fallback', () => {
    const meta = {
      default: 'en-US',
      locales: {
        'en-US': { label: 'English' },
        'de-DE': { label: 'Deutsch' },
        'es-ES': { label: 'Español (España)' },
        'zh-CN': { label: '中文' },
        'fr-FR': { label: 'Français' },
        'ar-SA': { label: 'العربية', rtl: true },
        'th-TH': { label: 'ไทย', rtl: false },
        'ur-PK': { label: 'اردو', rtl: true },
      },
    };

    jest.isolateModules(() => {
      // Prevent client i18n initialization in tests
      const globalAny = global as any;
      const prevWindow = globalAny.window;
      delete globalAny.window;
      process.env.NEXT_PUBLIC_I18N_META = JSON.stringify(meta);

      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mod = require('../i18n') as typeof import('../i18n');
      const { normalizeLanguage } = mod;

      expect(normalizeLanguage(undefined)).toBe('en-US');
      expect(normalizeLanguage('en')).toBe('en-US');
      expect(normalizeLanguage('en-GB')).toBe('en-US');
      expect(normalizeLanguage('es')).toBe('es-ES');
      expect(normalizeLanguage('es-ES')).toBe('es-ES');
      expect(normalizeLanguage('es-MX')).toBe('es-ES');
      expect(normalizeLanguage('zh')).toBe('zh-CN');
      expect(normalizeLanguage('fr')).toBe('fr-FR');
      expect(normalizeLanguage('fr-CA')).toBe('fr-FR');
      expect(normalizeLanguage('de')).toBe('de-DE');
      expect(normalizeLanguage('de-AT')).toBe('de-DE');
      for (const language of ['ur', 'ur-PK', 'ur_IN', 'UR_pk']) {
        expect(normalizeLanguage(language)).toBe('ur-PK');
      }

      // restore window to avoid side effects
      globalAny.window = prevWindow;
    });
  });

  test('exposes the requested language while an async switch is pending', async () => {
    const globalAny = global as any;
    const prevWindow = globalAny.window;
    delete globalAny.window;
    jest.resetModules();

    let resolveChange!: () => void;
    const languageChange = new Promise<void>(resolve => {
      resolveChange = resolve;
    });

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mockedI18n = require('i18next') as { changeLanguage: jest.Mock };
    mockedI18n.changeLanguage.mockReturnValueOnce(languageChange);

    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const runtimeI18n = require('../i18n')
        .default as typeof import('../i18n').default;
      /* eslint-disable @typescript-eslint/no-require-imports */
      const requestLanguageModule =
        require('../lib/request-language') as typeof import('../lib/request-language');
      /* eslint-enable @typescript-eslint/no-require-imports */
      const { getPendingRequestLanguage } = requestLanguageModule;

      const changePromise = runtimeI18n.changeLanguage('fr-FR');

      expect(getPendingRequestLanguage()).toBe('fr-FR');

      resolveChange();
      await changePromise;

      expect(getPendingRequestLanguage()).toBe('');
    } finally {
      globalAny.window = prevWindow;
    }
  });

  test('keeps an explicit pending language when an argumentless switch completes', async () => {
    const globalAny = global as any;
    const prevWindow = globalAny.window;
    delete globalAny.window;
    jest.resetModules();

    let resolveExplicitChange!: () => void;
    const explicitLanguageChange = new Promise<void>(resolve => {
      resolveExplicitChange = resolve;
    });

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mockedI18n = require('i18next') as { changeLanguage: jest.Mock };
    mockedI18n.changeLanguage
      .mockReturnValueOnce(explicitLanguageChange)
      .mockResolvedValueOnce(undefined);

    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const runtimeI18n = require('../i18n')
        .default as typeof import('../i18n').default;
      /* eslint-disable @typescript-eslint/no-require-imports */
      const requestLanguageModule =
        require('../lib/request-language') as typeof import('../lib/request-language');
      /* eslint-enable @typescript-eslint/no-require-imports */
      const { getPendingRequestLanguage } = requestLanguageModule;

      const explicitChangePromise = runtimeI18n.changeLanguage('fr-FR');
      expect(getPendingRequestLanguage()).toBe('fr-FR');

      await runtimeI18n.changeLanguage();
      expect(getPendingRequestLanguage()).toBe('fr-FR');

      resolveExplicitChange();
      await explicitChangePromise;
      expect(getPendingRequestLanguage()).toBe('');
    } finally {
      globalAny.window = prevWindow;
    }
  });

  test('persists an Urdu preference after a successful switch', async () => {
    jest.resetModules();
    process.env.NEXT_PUBLIC_I18N_META = JSON.stringify({
      default: 'en-US',
      locales: {
        'en-US': { label: 'English' },
        'ur-PK': { label: 'اردو', rtl: true },
      },
    });
    window.localStorage.removeItem('preferred_language');
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mocked = require('i18next') as {
      isInitialized: boolean;
      changeLanguage: jest.Mock;
      use: jest.Mock;
      init: jest.Mock;
    };
    mocked.isInitialized = true;
    mocked.changeLanguage.mockResolvedValueOnce(undefined);
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const runtime = require('../i18n')
      .default as typeof import('../i18n').default;
    await runtime.changeLanguage('ur_IN');
    expect(window.localStorage.getItem('preferred_language')).toBe('ur-PK');
    jest.resetModules();
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const reloaded = require('i18next') as typeof mocked;
    reloaded.isInitialized = false;
    reloaded.use = jest.fn(() => reloaded);
    reloaded.init = jest.fn(() => Promise.resolve());
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    require('../i18n');
    expect(reloaded.init).toHaveBeenCalledWith(
      expect.objectContaining({ lng: 'ur-PK' }),
    );
    window.localStorage.removeItem('preferred_language');
  });

  test('does not persist a preferred language when the switch fails', async () => {
    jest.resetModules();
    window.localStorage.setItem('preferred_language', 'zh-CN');

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mockedI18n = require('i18next') as {
      changeLanguage: jest.Mock;
      init?: jest.Mock;
      isInitialized?: boolean;
      use?: jest.Mock;
    };
    mockedI18n.isInitialized = false;
    mockedI18n.use = jest.fn(() => mockedI18n);
    mockedI18n.init = jest.fn(() => Promise.resolve());
    mockedI18n.changeLanguage.mockRejectedValueOnce(new Error('load failed'));
    const consoleErrorSpy = jest
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);

    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const runtimeI18n = require('../i18n')
        .default as typeof import('../i18n').default;

      await expect(runtimeI18n.changeLanguage('fr-FR')).rejects.toThrow(
        'load failed',
      );

      expect(window.localStorage.getItem('preferred_language')).toBe('zh-CN');
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  test('locale helpers expose labels from injected metadata', async () => {
    const meta = {
      default: 'en-US',
      locales: {
        'en-US': { label: 'English' },
        'zh-CN': { label: '中文' },
        'fr-FR': { label: 'Français' },
        'ar-SA': { label: 'العربية', rtl: true },
        'th-TH': { label: 'ไทย', rtl: false },
        'ur-PK': { label: 'اردو', rtl: true },
      },
      namespaces: ['common.core'],
    };

    jest.resetModules();
    process.env.NEXT_PUBLIC_I18N_META = JSON.stringify(meta);

    const { getLocaleLabel, isRtlLocale, localeEntries, namespaces } =
      await import('../lib/i18n-locales');

    expect(localeEntries.map(([code]) => code)).toEqual([
      'en-US',
      'zh-CN',
      'fr-FR',
      'ar-SA',
      'th-TH',
      'ur-PK',
    ]);
    expect(getLocaleLabel('fr-FR')).toBe('Français');
    expect(isRtlLocale('ar-SA')).toBe(true);
    expect(getLocaleLabel('ur-PK')).toBe('اردو');
    expect(isRtlLocale('ur-PK')).toBe(true);
    expect(isRtlLocale('th-TH')).toBe(false);
    expect(namespaces).toEqual(['common.core']);
  });
});
