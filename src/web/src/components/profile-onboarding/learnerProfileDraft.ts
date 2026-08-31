import type { LearnerProfile } from '@/api/learnerProfile';

type TranslateLegacyValue = (key: string, options: { value: string }) => string;

const LEGACY_PREFILL_FIELDS = [
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

export type LearnerNicknameSource =
  | 'canonical'
  | 'legacy-migration'
  | 'legacy-compat'
  | 'unavailable';

export type LearnerNicknameDraft = {
  value: string;
  savedValue: string | undefined;
  source: LearnerNicknameSource;
};

export const resolveLearnerNicknameDraft = (
  profile: LearnerProfile,
): LearnerNicknameDraft => {
  const hasCanonicalNickname = Object.prototype.hasOwnProperty.call(
    profile,
    'nickname',
  );
  const savedValue = hasCanonicalNickname
    ? String(profile.nickname ?? '').trim()
    : undefined;
  const legacyValue = (
    profile.legacy_profile_values?.sys_user_nickname ?? ''
  ).trim();

  if (savedValue) {
    return { value: savedValue, savedValue, source: 'canonical' };
  }
  if (legacyValue) {
    return {
      value: legacyValue,
      savedValue,
      source: hasCanonicalNickname ? 'legacy-migration' : 'legacy-compat',
    };
  }
  return {
    value: '',
    savedValue,
    source: hasCanonicalNickname ? 'canonical' : 'unavailable',
  };
};

export const resolveLearnerNickname = (profile: LearnerProfile): string =>
  resolveLearnerNicknameDraft(profile).value;
