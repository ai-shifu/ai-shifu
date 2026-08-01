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
        'zh-CN': { label: '中文' },
        'fr-FR': { label: 'Français' },
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
      expect(normalizeLanguage('zh')).toBe('zh-CN');
      expect(normalizeLanguage('fr')).toBe('fr-FR');
      expect(normalizeLanguage('fr-CA')).toBe('fr-FR');
      expect(normalizeLanguage('de')).toBe('en-US');

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

  test('locale helpers expose labels from injected metadata', async () => {
    const meta = {
      default: 'en-US',
      locales: {
        'en-US': { label: 'English' },
        'zh-CN': { label: '中文' },
        'fr-FR': { label: 'Français' },
      },
      namespaces: ['common.core'],
    };

    jest.resetModules();
    process.env.NEXT_PUBLIC_I18N_META = JSON.stringify(meta);

    const { getLocaleLabel, localeEntries, namespaces } =
      await import('../lib/i18n-locales');

    expect(localeEntries.map(([code]) => code)).toEqual([
      'en-US',
      'zh-CN',
      'fr-FR',
    ]);
    expect(getLocaleLabel('fr-FR')).toBe('Français');
    expect(namespaces).toEqual(['common.core']);
  });
});
