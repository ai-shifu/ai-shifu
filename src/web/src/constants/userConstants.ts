export const SEX = {
  MALE: 'male',
  FEMALE: 'female',
  SECRET: 'secret',
};

export const SEX_NAMES = {
  [SEX.MALE]: '男性',
  [SEX.FEMALE]: '女性',
  [SEX.SECRET]: '保密'
};

export const LANGUAGE_DICT = {
  'zh-CN': '中文',
  'en-US': 'English'
}

export const selectDefaultLanguage = (language) => {
  if (language.includes('en')) {
    return 'en-US';
  }

  return 'zh-CN';
}

// Map browser language to course language
export const selectCourseLanguage = (language) => {
  // Common language mappings
  const languageMap = {
    'zh-CN': '中文',
    'zh-TW': '繁體中文',
    'zh-HK': '繁體中文',
    'zh': '中文',
    'en-US': 'English',
    'en-GB': 'English',
    'en': 'English',
    'ja': '日本語',
    'ko': '한국어',
    'fr': 'Français',
    'de': 'Deutsch',
    'es': 'Español',
    'pt': 'Português',
    'ru': 'Русский',
    'ar': 'العربية',
    'hi': 'हिन्दी',
    'it': 'Italiano',
    'nl': 'Nederlands',
    'pl': 'Polski',
    'tr': 'Türkçe',
    'vi': 'Tiếng Việt',
    'th': 'ไทย',
    'id': 'Bahasa Indonesia',
    'ms': 'Bahasa Melayu'
  };

  // Try exact match first
  if (languageMap[language]) {
    return languageMap[language];
  }

  // Try language code without region (e.g., 'en-CA' -> 'en')
  const langCode = language.split('-')[0];
  if (languageMap[langCode]) {
    return languageMap[langCode];
  }

  // Default to English for any unmapped language
  return 'English';
}
