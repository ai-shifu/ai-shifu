import apiService from '@/api';

/**
 * Ask the backend which domain a pending Google login should return to.
 *
 * All domains share one Google callback, because Google does not accept
 * wildcards in a client's authorized redirect URIs. The backend validates the
 * origin recorded in the signed state against the domains we actually serve, so
 * the answer is safe to redirect to; an empty string means "stay here". Never
 * blocks the login: a slow or failing lookup falls back to finishing here.
 */
const RESOLVE_TIMEOUT_MS = 5000;

function withTimeout<T>(promise: Promise<T>, fallback: T): Promise<T> {
  return new Promise<T>(resolve => {
    const timer = setTimeout(() => resolve(fallback), RESOLVE_TIMEOUT_MS);
    promise
      .then(value => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch(() => {
        clearTimeout(timer);
        resolve(fallback);
      });
  });
}

export async function resolveGoogleCallbackOrigin(
  state: string,
): Promise<string> {
  try {
    const response = (await withTimeout(
      Promise.resolve(apiService.googleOauthCallbackOrigin({ state })),
      null,
    )) as
      | { code?: number; data?: { origin?: string } }
      | { origin?: string }
      | null;

    if (!response) {
      // Timed out. Completing the login on this domain is the safe default:
      // the user is signed in, just not handed back to the custom domain.
      console.warn('[Google OAuth] return-origin lookup timed out');
      return '';
    }

    const payload =
      response && typeof response === 'object' && 'data' in response
        ? (response as { data?: { origin?: string } }).data
        : (response as { origin?: string });

    return String(payload?.origin || '').trim();
  } catch (error) {
    // Staying on this domain still completes the login for the common case,
    // so a failed lookup must not abort the flow.
    console.warn('[Google OAuth] could not resolve return origin', error);
    return '';
  }
}
