jest.unmock('i18next');

import i18next from 'i18next';
import ICU from 'i18next-icu';

import arHeader from '../../../i18n/ar-SA/components/header.json';
import arAuth from '../../../i18n/ar-SA/modules/auth.json';
import arBilling from '../../../i18n/ar-SA/modules/billing.json';
import arSettings from '../../../i18n/ar-SA/modules/settings.json';

describe('Arabic temporal plural translations', () => {
  const i18n = i18next.createInstance().use(new ICU());

  beforeAll(async () => {
    await i18n.init({
      lng: 'ar-SA',
      fallbackLng: false,
      resources: {
        'ar-SA': {
          translation: {
            component: { header: arHeader },
            module: {
              auth: arAuth,
              billing: arBilling,
              settings: arSettings,
            },
          },
        },
      },
    });
  });

  test('selects distinct month and year forms', () => {
    expect(
      i18n.t('module.billing.package.validityShort.monthly', { count: 1 }),
    ).toBe('شهر واحد');
    expect(
      i18n.t('module.billing.package.validityShort.monthly', { count: 2 }),
    ).toBe('شهران');
    expect(
      i18n.t('module.billing.package.validityShort.monthly', { count: 3 }),
    ).toContain('أشهر');
    expect(
      i18n.t('module.billing.package.validityShort.monthly', { count: 11 }),
    ).toContain('شهرًا');
    expect(
      i18n.t('module.billing.package.validityShort.yearly', { count: 2 }),
    ).toBe('سنتان');
  });

  test('uses the correct dual forms inside surrounding sentences', () => {
    expect(i18n.t('module.billing.package.validity.free', { days: 2 })).toBe(
      'الصلاحية: تسري ليومين من تاريخ التسجيل',
    );
    expect(i18n.t('component.header.daysAgo', { count: 2 })).toBe('منذ يومين');
    expect(i18n.t('module.auth.secondsLater', { count: 2 })).toBe(
      'إعادة الإرسال بعد ثانيتين',
    );
  });

  test('formats few and many categories without dropping other values', () => {
    expect(i18n.t('component.header.minutesAgo', { count: 3 })).toContain(
      'دقائق',
    );
    expect(i18n.t('module.settings.resendCountdown', { count: 11 })).toContain(
      'ثانيةً',
    );
    expect(
      i18n.t('module.billing.welcomeTrial.description', {
        days: 3,
        credits: 100,
      }),
    ).toContain('100 رصيدًا');
  });
});
