jest.unmock('i18next');

import i18next from 'i18next';
import ICU from 'i18next-icu';
import enProfile from '../../../../i18n/en-US/modules/profile-onboarding.json';
import frProfile from '../../../../i18n/fr-FR/modules/profile-onboarding.json';
import zhProfile from '../../../../i18n/zh-CN/modules/profile-onboarding.json';
import { buildLearnerProfileDraft } from './learnerProfileDraft';

const emptyProfileWithLegacyValues = {
  learner_profile: '',
  learner_profile_updated_at: null,
  has_learner_profile: false,
  max_length: 1000,
  legacy_profile_values: {
    sys_user_nickname: '小林',
    sys_user_background: '办公室工作',
    sys_user_style: '亲切直接',
  },
};

describe('buildLearnerProfileDraft', () => {
  test.each([
    [
      'zh-CN',
      zhProfile,
      '可以叫我 小林。\n我的背景：办公室工作\n我喜欢的语言风格：亲切直接',
    ],
    [
      'en-US',
      enProfile,
      'You can call me 小林.\nMy background: 办公室工作\nMy preferred language style: 亲切直接',
    ],
    [
      'fr-FR',
      frProfile,
      'Vous pouvez m’appeler 小林.\nMon parcours : 办公室工作\nMon style de langage préféré : 亲切直接',
    ],
  ])(
    'interpolates legacy values with the production ICU formatter in %s',
    async (locale, profileTranslations, expected) => {
      const i18n = i18next.createInstance().use(new ICU());
      await i18n.init({
        lng: locale,
        resources: {
          [locale]: {
            translation: {
              module: {
                profileOnboarding: profileTranslations,
              },
            },
          },
        },
      });

      const draft = buildLearnerProfileDraft(
        emptyProfileWithLegacyValues,
        (key, options) => i18n.t(key, options),
      );

      expect(draft).toBe(expected);
      expect(draft).not.toContain('{{value}}');
      expect(draft).not.toContain('{value}');
    },
  );
});
