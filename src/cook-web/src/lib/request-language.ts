let pendingRequestLanguage = '';

export const getPendingRequestLanguage = () => pendingRequestLanguage;

export const setPendingRequestLanguage = (language?: string | null) => {
  // A relearn can start a new /run before i18next finishes loading the
  // selected locale, so request code needs the user's intent synchronously.
  pendingRequestLanguage = String(language || '').trim();
};

export const clearPendingRequestLanguage = (language?: string | null) => {
  const normalizedLanguage = String(language || '').trim();
  if (!normalizedLanguage || pendingRequestLanguage === normalizedLanguage) {
    pendingRequestLanguage = '';
  }
};
