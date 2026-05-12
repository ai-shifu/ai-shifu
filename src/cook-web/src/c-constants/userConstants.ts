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

export const LANGUAGE_DICT = {
  'zh-CN': '中文',
  'en-US': 'English',
  'fr-FR': 'Français',
};

export const selectDefaultLanguage = language => {
  if (language.includes('en')) {
    return 'en-US';
  }
  if (language.includes('fr')) {
    return 'fr-FR';
  }

  return 'zh-CN';
};
