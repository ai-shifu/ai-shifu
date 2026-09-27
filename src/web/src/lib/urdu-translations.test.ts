jest.unmock('i18next');

import i18next from 'i18next';
import ICU from 'i18next-icu';
import core from '../../../i18n/ur-PK/common/core.json';
import header from '../../../i18n/ur-PK/components/header.json';
import auth from '../../../i18n/ur-PK/modules/auth.json';
import billing from '../../../i18n/ur-PK/modules/billing.json';
import chat from '../../../i18n/ur-PK/modules/chat.json';
import operationsOrder from '../../../i18n/ur-PK/modules/operations-order.json';
import profileOnboarding from '../../../i18n/ur-PK/modules/profile-onboarding.json';
import shifuSetting from '../../../i18n/ur-PK/modules/shifu-setting.json';
import { LIVE_VOICE_STYLE_I18N_KEYS } from '../components/shifu-setting/live-voice-style';

const i18n = i18next.createInstance().use(new ICU());

beforeAll(async () => {
  await i18n.init({
    lng: 'ur-PK',
    fallbackLng: false,
    resources: {
      'ur-PK': {
        translation: {
          common: { core },
          component: { header },
          module: {
            auth,
            billing,
            chat,
            operationsOrder,
            profileOnboarding,
            shifuSetting,
          },
        },
      },
    },
  });
});

test.each([0, 1, 2, 11, 100])(
  'formats Urdu counts and durations for %s',
  count => {
    const formattedCount = new Intl.NumberFormat('ur-PK').format(count);
    expect(i18n.t('module.operationsOrder.totalCount', { count })).toBe(
      `کل ${formattedCount} ${count === 1 ? 'آرڈر' : 'آرڈرز'}`,
    );
    expect(i18n.t('component.header.daysAgo', { count })).toContain(
      String(count),
    );
    expect(i18n.t('module.auth.secondsLater', { count })).toContain(
      String(count),
    );
    expect(
      i18n.t('module.billing.package.validityShort.monthly', { count }),
    ).toContain(String(count));
  },
);

test('keeps learner copy and interpolation in Urdu', () => {
  expect(i18n.t('module.chat.ask')).toBe('مزید پوچھیں');
  expect(
    i18n.t('module.profileOnboarding.characterCount', { count: 12, max: 100 }),
  ).toBe('12 / 100 حروف درج کیے گئے');
  expect(
    i18n.t('common.core.shareCourseMessage', { courseName: 'Course 1' }),
  ).toContain('Course 1');
  expect(i18n.t('common.core.legalFallbackEnglishNotice')).toContain('انگریزی');
});

test('preserves executable MarkdownFlow syntax in the onboarding prompt', () => {
  const prompt = profileOnboarding.admin.defaultMarkdownflow;
  expect(prompt).toContain('?[%{{sys_user_nickname}}...');
  expect(prompt.match(/\?\[/g)).toHaveLength(3);
  expect(prompt).not.toMatch(/\u061f\[/);
  expect(prompt).not.toMatch(/[\u3400-\u9fff]/);
});

test('gives each selectable live voice style a distinct Urdu label', () => {
  const labels = Object.values(LIVE_VOICE_STYLE_I18N_KEYS).map(key => {
    const label = i18n.t(key);
    expect(label).not.toBe(key);
    return label;
  });
  expect(new Set(labels).size).toBe(labels.length);
});
