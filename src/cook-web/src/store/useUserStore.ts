import { create } from 'zustand';
import { getUserInfo, registerTmp } from '@/c-api/user';
import { tokenTool } from '@/c-service/storeUtil';
import { genUuid } from '@/c-utils/common';
import { subscribeWithSelector } from 'zustand/middleware';

import { removeParamFromUrl } from '@/c-utils/urlUtils';
import i18n from '@/i18n';
import { UserStoreState } from '@/c-types/store';
import { clearGoogleOAuthSession } from '@/lib/google-oauth-session';

// Helper function to register as guest user
const registerAsGuest = async (): Promise<string> => {
  // Always fetch a fresh guest token to avoid expiration issues
  tokenTool.remove();
  const res = await registerTmp({ temp_id: genUuid() });
  const token = res.token;
  tokenTool.set({ token, faked: true });
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
      const resetLogoutFlag = () => {
        if (typeof window !== 'undefined') {
          (window as any).__IS_LOGGING_OUT__ = false;
        }
      };

      if (typeof window !== 'undefined') {
        (window as any).__IS_LOGGING_OUT__ = true;
      }

      try {
        clearGoogleOAuthSession();
        await registerAsGuest();
        set(() => ({
          userInfo: null,
        }));

        get()._updateUserStatus();

        if (reload && typeof window !== 'undefined') {
          const url = removeParamFromUrl(window.location.href, [
            'code',
            'state',
            'redirect',
          ]);
          window.location.assign(url);
          didTriggerReload = true;
        }
      } finally {
        if (!didTriggerReload) {
          resetLogoutFlag();
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
          if (normalizedUserInfo?.language) {
            i18n.changeLanguage(normalizedUserInfo.language);
          }
        } catch (err) {
          const error = err as any;
          const latestTokenData = tokenTool.get();
          tokenChangedDuringFetch =
            !!latestTokenData.token && latestTokenData.token !== initialToken;

          if (tokenChangedDuringFetch) {
            return;
          }

          // Only reset to guest if it's a clear authentication error (not network or server issues)
          if (
            error?.status === 403 ||
            error?.code === 1005 ||
            error?.code === 1001
          ) {
            if (!latestTokenData.faked) {
              await registerAsGuest();
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
      set(state => ({
        userInfo: {
          ...state.userInfo,
          ...userInfo,
        },
      }));
    },

    // Public API: Refresh user information from server
    refreshUserInfo: async () => {
      const res = await getUserInfo();
      set(() => ({
        userInfo: {
          ...res,
        },
      }));

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
