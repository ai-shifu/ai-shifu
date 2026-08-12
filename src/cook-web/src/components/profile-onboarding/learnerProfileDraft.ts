import type { LearnerProfile } from '@/api/learnerProfile';

type TranslateLegacyValue = (key: string, options: { value: string }) => string;

const LEGACY_PREFILL_FIELDS = [
  [
    'sys_user_nickname',
    'module.profileOnboarding.dialog.legacyPrefill.nickname',
  ],
  [
    'sys_user_background',
    'module.profileOnboarding.dialog.legacyPrefill.background',
  ],
  ['sys_user_style', 'module.profileOnboarding.dialog.legacyPrefill.style'],
] as const;

export const buildLearnerProfileDraft = (
  profile: LearnerProfile,
  translate: TranslateLegacyValue,
): string => {
  const canonicalProfile = profile.learner_profile.trim();
  if (canonicalProfile) {
    return canonicalProfile;
  }

  return LEGACY_PREFILL_FIELDS.flatMap(([legacyKey, translationKey]) => {
    const value = profile.legacy_profile_values?.[legacyKey]?.trim();
    return value ? [translate(translationKey, { value })] : [];
  }).join('\n');
};
