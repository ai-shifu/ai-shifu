import { getLocaleLabel, localeCodes } from '@/lib/i18n-locales';

export const SEX = {
  MALE: 'male',
  FEMALE: 'female',
  SECRET: 'secret',
};

export const SEX_NAMES = {
  [SEX.MALE]: '男性',
  [SEX.FEMALE]: '女性',
  [SEX.SECRET]: '保密',
};

export const LANGUAGE_DICT = Object.fromEntries(
  localeCodes.map(code => [code, getLocaleLabel(code)]),
);

export const selectDefaultLanguage = language => {
  const normalized = String(language ?? '')
    .trim()
    .replace('_', '-')
    .toLowerCase();

  if (normalized.startsWith('en')) {
    return 'en-US';
  }
  if (normalized.startsWith('fr')) {
    return 'fr-FR';
  }

  return 'zh-CN';
};
