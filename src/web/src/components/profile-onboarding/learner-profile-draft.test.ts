import {
  resolveLearnerNickname,
  resolveLearnerNicknameDraft,
} from './learner-profile-draft';

const emptyProfileWithLegacyValues = {
  learner_profile: '',
  learner_profile_updated_at: null,
  has_learner_profile: false,
  max_length: 1000,
  legacy_profile_values: {
    sys_user_nickname: '小林',
  },
};

describe('learner nickname draft', () => {
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
