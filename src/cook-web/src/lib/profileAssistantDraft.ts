// Adapted from the account-scoped paste draft helpers in split-source 331a54f53.
const LEGACY_KEY = 'profile-onboarding-paste-draft:profile-v2';
const PREFIX = `${LEGACY_KEY}:`;
const ACTIVE_KEY = 'profile-onboarding-paste-draft:active-user:profile-v2';
const storageKey = (scope: string) =>
  scope.trim() ? `${PREFIX}${encodeURIComponent(scope.trim())}` : '';

export const readProfileAssistantDraft = (scope: string): string => {
  if (typeof window === 'undefined') return '';
  try {
    window.sessionStorage.removeItem(LEGACY_KEY);
    const previous = window.sessionStorage.getItem(ACTIVE_KEY);
    const key = storageKey(scope);
    if (previous && previous !== key && previous.startsWith(PREFIX)) {
      window.sessionStorage.removeItem(previous);
    }
    if (!key) {
      window.sessionStorage.removeItem(ACTIVE_KEY);
      return '';
    }
    window.sessionStorage.setItem(ACTIVE_KEY, key);
    return window.sessionStorage.getItem(key) || '';
  } catch {
    return '';
  }
};

export const writeProfileAssistantDraft = (scope: string, draft: string) => {
  if (typeof window === 'undefined' || !storageKey(scope)) return;
  try {
    if (draft) window.sessionStorage.setItem(storageKey(scope), draft);
    else window.sessionStorage.removeItem(storageKey(scope));
  } catch {
    // Storage may be unavailable in restricted browser modes.
  }
};

export const clearProfileAssistantDrafts = () => {
  readProfileAssistantDraft('');
};
