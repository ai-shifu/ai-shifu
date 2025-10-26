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
        'qps-ploc': { label: 'Pseudo' },
      },
    };

    jest.isolateModules(() => {
      // Prevent client i18n initialization in tests
      // @ts-expect-error: simulate non-browser environment for test
      const prevWindow = global.window;
      // @ts-expect-error: delete window to force SSR path in module under test
      delete (global as any).window;
      process.env.NEXT_PUBLIC_I18N_META = JSON.stringify(meta);

      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mod = require('../i18n') as typeof import('../i18n');
      const { normalizeLanguage } = mod;

      expect(normalizeLanguage(undefined)).toBe('en-US');
      expect(normalizeLanguage('en')).toBe('en-US');
      expect(normalizeLanguage('en-GB')).toBe('en-US');
      expect(normalizeLanguage('zh')).toBe('zh-CN');
      expect(normalizeLanguage('fr')).toBe('en-US');

      // restore window to avoid side effects
      // @ts-expect-error: restore window that we deleted intentionally above
      global.window = prevWindow;
    });
  });
});
