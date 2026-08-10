const FIXED_PROFILE_KEYS = new Set([
  'sys_user_nickname',
  'avatar',
  'sex',
  'birth',
]);

const HIDDEN_PROFILE_KEYS = new Set([
  'language',
  'sys_user_background',
  'sys_user_style',
]);

export const shouldShowDynamicProfileField = (key: string) =>
  !FIXED_PROFILE_KEYS.has(key) && !HIDDEN_PROFILE_KEYS.has(key);
