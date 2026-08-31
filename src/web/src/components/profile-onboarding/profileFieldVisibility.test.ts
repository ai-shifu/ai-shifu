import { shouldShowDynamicProfileField } from './profileFieldVisibility';

describe('shouldShowDynamicProfileField', () => {
  test.each(['sys_user_background', 'sys_user_style'])(
    'always hides deprecated learner-profile field %s',
    key => {
      expect(shouldShowDynamicProfileField(key)).toBe(false);
    },
  );

  test('keeps account fields separate and course custom fields visible', () => {
    expect(shouldShowDynamicProfileField('sys_user_nickname')).toBe(false);
    expect(shouldShowDynamicProfileField('language')).toBe(false);
    expect(shouldShowDynamicProfileField('course_learning_goal')).toBe(true);
  });
});
