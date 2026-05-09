import { create } from 'zustand';
import { getUserInfo, registerTmp } from '@/c-api/user';
import { tokenTool } from '@/c-service/storeUtil';
import { genUuid } from '@/c-utils/common';
import { subscribeWithSelector } from 'zustand/middleware';

import { debugError, debugInfo, debugWarn } from '@/c-utils/debugConsole';
import { removeParamFromUrl } from '@/c-utils/urlUtils';
import i18n from '@/i18n';
import { UserStoreState } from '@/c-types/store';
import { clearGoogleOAuthSession } from '@/lib/google-oauth-session';
import { identifyUmamiUser } from '@/c-common/tools/tracking';

const GUEST_TEMP_ID_KEY = 'guest_temp_id';

const rotateGuestTempId = (): void => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    localStorage.setItem(GUEST_TEMP_ID_KEY, genUuid());
  } catch {
    // Ignore storage errors in restricted browser modes.
  }
};

const getGuestTempId = (): string => {
  if (typeof window === 'undefined') {
    return genUuid();
  }
  try {
    const cached = localStorage.getItem(GUEST_TEMP_ID_KEY);
    if (cached && cached.trim()) {
      return cached;
    }
    const nextId = genUuid();
    localStorage.setItem(GUEST_TEMP_ID_KEY, nextId);
    return nextId;
  } catch {
    return genUuid();
  }
};

// Helper function to register as guest user
const registerAsGuest = async (): Promise<string> => {
  // Always fetch a fresh guest token to avoid expiration issues
  debugInfo('[auth-chain] register guest start', {
    hasExistingToken: Boolean(tokenTool.get().token),
  });
  tokenTool.remove();
  const tempId = getGuestTempId();
  const res = await registerTmp({ temp_id: tempId });
  identifyUmamiUser(res?.userInfo);
  const token = res.token;
  tokenTool.set({ token, faked: true });
  debugInfo('[auth-chain] register guest success', {
    tempId,
    hasToken: Boolean(token),
  });
  return token;
};

export const useUserStore = create<
  UserStoreState,
  [['zustand/subscribeWithSelector', never]]
>(
  subscribeWithSelector((set, get) => ({
    userInfo: null,
    isGuest: false,
    isLoggedIn: false,
    isInitialized: false,
    _initializingPromise: null as Promise<void> | null,

    // Internal method: Update user status based on token
    _updateUserStatus: () => {
      const tokenData = tokenTool.get();
      if (tokenData.token) {
        set({
          isGuest: tokenData.faked,
          isLoggedIn: !tokenData.faked,
          isInitialized: true,
        });
      } else {
        set({
          isGuest: false,
          isLoggedIn: false,
          isInitialized: true,
        });
      }
    },

    // Public API: Login with user credentials
    login: async (userInfo: any, token: string) => {
      // Prevent future guest registration from resolving back to this
      // authenticated account via stale temp_id mapping.
      rotateGuestTempId();
      tokenTool.set({ token, faked: false });

      const normalizedUserInfo = {
        ...userInfo,
      };

      if (!normalizedUserInfo.name && normalizedUserInfo.email) {
        normalizedUserInfo.name = normalizedUserInfo.email.split('@')[0];
      }
      if (!normalizedUserInfo.avatar && normalizedUserInfo.user_avatar) {
        normalizedUserInfo.avatar = normalizedUserInfo.user_avatar;
      }

      set(() => ({
        userInfo: normalizedUserInfo,
      }));
      identifyUmamiUser(normalizedUserInfo);

      // Let i18next handle the language and its fallback mechanism
      if (normalizedUserInfo.language) {
        i18n.changeLanguage(normalizedUserInfo.language);
      }

      get()._updateUserStatus();

      if (typeof window !== 'undefined') {
        const cleanedUrl = removeParamFromUrl(window.location.href, [
          'code',
          'state',
          'redirect',
        ]);
        if (cleanedUrl !== window.location.href) {
          window.history.replaceState(null, '', cleanedUrl);
        }
      }
    },

    // Public API: Logout user
    logout: async (reload = true) => {
      let didTriggerReload = false;
      const tokenDataBeforeLogout = tokenTool.get();
      debugWarn('[auth-chain] logout start', {
        reload,
        isGuestBeforeLogout: tokenDataBeforeLogout.faked,
        hasTokenBeforeLogout: Boolean(tokenDataBeforeLogout.token),
      });
      const resetLogoutFlag = () => {
        if (typeof window !== 'undefined') {
          (window as any).__IS_LOGGING_OUT__ = false;
        }
      };

      if (typeof window !== 'undefined') {
        (window as any).__IS_LOGGING_OUT__ = true;
      }

      try {
        // Keep temp_id only for guest-session auth recovery flows.
        if (reload || !tokenDataBeforeLogout.faked) {
          rotateGuestTempId();
          debugInfo(
            '[auth-chain] rotated guest temp id before logout recovery',
            {
              reload,
              wasGuest: tokenDataBeforeLogout.faked,
            },
          );
        }
        clearGoogleOAuthSession();
        await registerAsGuest();
        set(() => ({
          userInfo: null,
        }));

        get()._updateUserStatus();
        debugInfo('[auth-chain] logout state switched to guest session', {
          reload,
        });

        if (reload && typeof window !== 'undefined') {
          const url = removeParamFromUrl(window.location.href, [
            'code',
            'state',
            'redirect',
          ]);
          debugWarn('[auth-chain] logout page reload start', {
            targetUrl: url,
          });
          window.location.assign(url);
          didTriggerReload = true;
        }
      } catch (logoutError) {
        debugError('[auth-chain] logout failed', logoutError);
        throw logoutError;
      } finally {
        if (!didTriggerReload) {
          resetLogoutFlag();
          debugInfo('[auth-chain] logout flag reset without page reload');
        }
      }
    },

    // Public API: Get token
    getToken: () => {
      return tokenTool.get().token || '';
    },

    // Public API: Initialize user session (call once on app start)
    initUser: async () => {
      // Check if already initialized
      if (get().isInitialized) {
        return;
      }

      // Prevent concurrent calls
      const existingPromise = get()._initializingPromise;
      if (existingPromise) {
        return existingPromise;
      }

      const initPromise = (async () => {
        const tokenData = tokenTool.get();
        const initialToken = tokenData.token;
        let tokenChangedDuringFetch = false;
        debugInfo('[auth-chain] initUser start', {
          hasInitialToken: Boolean(initialToken),
          isGuestToken: tokenData.faked,
        });

        try {
          // If no token, register as guest
          if (!initialToken) {
            await registerAsGuest();
            set(() => ({
              userInfo: null,
            }));
            return;
          }

          const response = await getUserInfo();
          const normalizedUserInfo =
            response && typeof response === 'object' && 'data' in response
              ? ((response as { data?: unknown }).data ?? response)
              : response;

          const latestTokenData = tokenTool.get();
          tokenChangedDuringFetch =
            !!latestTokenData.token && latestTokenData.token !== initialToken;

          // Another login just updated the token while this request was in flight
          // (common for OAuth flows). Respect the newer token and skip overwriting
          // state with stale guest data.
          if (tokenChangedDuringFetch) {
            debugInfo(
              '[auth-chain] initUser aborted because token changed during user info fetch',
            );
            return;
          }

          // Determine if user is authenticated based on mobile number or email
          const isAuthenticated = !!(
            normalizedUserInfo?.mobile || normalizedUserInfo?.email
          );
          tokenTool.set({
            token: latestTokenData.token || initialToken,
            faked: !isAuthenticated,
          });

          set(() => ({
            userInfo: normalizedUserInfo,
          }));
          identifyUmamiUser(normalizedUserInfo);
          if (normalizedUserInfo?.language) {
            i18n.changeLanguage(normalizedUserInfo.language);
          }
        } catch (err) {
          const error = err as any;
          const latestTokenData = tokenTool.get();
          tokenChangedDuringFetch =
            !!latestTokenData.token && latestTokenData.token !== initialToken;

          debugWarn('[auth-chain] initUser failed', {
            errorMessage: error?.message || String(err),
            errorCode: error?.code ?? '',
            errorStatus: error?.status ?? '',
            tokenChangedDuringFetch,
            latestTokenIsGuest: latestTokenData.faked,
            hasLatestToken: Boolean(latestTokenData.token),
          });

          if (tokenChangedDuringFetch) {
            debugInfo(
              '[auth-chain] initUser recovery skipped because token changed',
            );
            return;
          }

          // Only reset to guest if it's a clear authentication error (not network or server issues)
          if (
            error?.status === 403 ||
            error?.code === 1005 ||
            error?.code === 1001
          ) {
            debugWarn('[auth-chain] initUser entering auth recovery branch', {
              errorCode: error?.code ?? '',
              errorStatus: error?.status ?? '',
            });
            if (!latestTokenData.faked) {
              await registerAsGuest();
            } else {
              debugInfo(
                '[auth-chain] initUser kept current guest token because latest token is already marked as guest',
              );
            }
            set(() => ({
              userInfo: null,
            }));
          } else {
            // For other errors (network, server errors), preserve existing token state
            // but still update the status based on token data
            // eslint-disable-next-line no-console
            console.warn(
              'Failed to fetch user info, but preserving login state:',
              err,
            );
          }
        } finally {
          get()._updateUserStatus();
        }
      })();

      // Store the promise to prevent concurrent calls
      set({ _initializingPromise: initPromise });

      try {
        await initPromise;
      } finally {
        // Clear the promise when done
        set({ _initializingPromise: null });
      }
    },

    // Public API: Update user information
    updateUserInfo: userInfo => {
      const nextUserInfo = {
        ...get().userInfo,
        ...userInfo,
      };
      set(() => ({
        userInfo: nextUserInfo,
      }));
      identifyUmamiUser(nextUserInfo);
    },

    // Public API: Refresh user information from server
    refreshUserInfo: async () => {
      const res = await getUserInfo();
      set(() => ({
        userInfo: {
          ...res,
        },
      }));
      identifyUmamiUser(res);

      // Let i18next handle the language and its fallback mechanism
      i18n.changeLanguage(res.language);
    },

    ensureGuestToken: async () => {
      const tokenData = tokenTool.get();
      if (!tokenData.token) {
        await registerAsGuest();
      }
      get()._updateUserStatus();
    },
  })),
);
