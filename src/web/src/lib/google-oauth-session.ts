const STATE_KEY = 'google_oauth_state';
const REDIRECT_KEY = 'google_oauth_redirect';

const isBrowser = () =>
  typeof window !== 'undefined' && typeof sessionStorage !== 'undefined';

export const googleOAuthKeys = {
  state: STATE_KEY,
  redirect: REDIRECT_KEY,
};

export function setGoogleOAuthState(value: string) {
  if (!isBrowser()) return;
  sessionStorage.setItem(STATE_KEY, value);
}

export function getGoogleOAuthState(): string | null {
  if (!isBrowser()) return null;
  return sessionStorage.getItem(STATE_KEY);
}

export function setGoogleOAuthRedirect(value: string) {
  if (!isBrowser()) return;
  sessionStorage.setItem(REDIRECT_KEY, value);
}

export function getGoogleOAuthRedirect(): string | null {
  if (!isBrowser()) return null;
  return sessionStorage.getItem(REDIRECT_KEY);
}

export function clearGoogleOAuthSession() {
  if (!isBrowser()) return;
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(REDIRECT_KEY);
}
