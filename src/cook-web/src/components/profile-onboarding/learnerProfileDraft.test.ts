jest.unmock('i18next');

import i18next from 'i18next';
import ICU from 'i18next-icu';
import enProfile from '../../../../i18n/en-US/modules/profile-onboarding.json';
import frProfile from '../../../../i18n/fr-FR/modules/profile-onboarding.json';
import zhProfile from '../../../../i18n/zh-CN/modules/profile-onboarding.json';
import {
  buildLearnerProfileDraft,
  resolveLearnerNickname,
  resolveLearnerNicknameDraft,
} from './learnerProfileDraft';

const emptyProfileWithLegacyValues = {
  learner_profile: '',
  learner_profile_updated_at: null,
  has_learner_profile: false,
  max_length: 1000,
  legacy_profile_values: {
    sys_user_nickname: '小林',
    sys_user_style: '亲切直接',
  },
};

describe('buildLearnerProfileDraft', () => {
  test.each([
    ['zh-CN', zhProfile, '我喜欢的语言风格：亲切直接'],
    ['en-US', enProfile, 'My preferred language style: 亲切直接'],
    ['fr-FR', frProfile, 'Mon style de langage préféré : 亲切直接'],
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
      expect(resolveLearnerNickname(emptyProfileWithLegacyValues)).toBe('小林');
    },
  );

  test('prefers the canonical account nickname over the legacy variable', () => {
    expect(
      resolveLearnerNickname({
        ...emptyProfileWithLegacyValues,
        nickname: '小雨',
      }),
    ).toBe('小雨');
  });

  test('marks an explicit empty canonical nickname with a legacy value for migration', () => {
    expect(
      resolveLearnerNicknameDraft({
        ...emptyProfileWithLegacyValues,
        nickname: '',
      }),
    ).toEqual({
      value: '小林',
      savedValue: '',
      source: 'legacy-migration',
    });
  });

  test('does not auto-migrate a legacy nickname when the backend omits the canonical field', () => {
    expect(resolveLearnerNicknameDraft(emptyProfileWithLegacyValues)).toEqual({
      value: '小林',
      savedValue: undefined,
      source: 'legacy-compat',
    });
  });
});
