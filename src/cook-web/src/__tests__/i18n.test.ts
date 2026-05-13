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
