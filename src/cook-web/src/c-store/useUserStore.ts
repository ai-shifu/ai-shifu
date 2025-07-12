import { create } from 'zustand';
import { getUserInfo, registerTmp } from '@/c-api/user';
import { tokenTool } from '@/c-service/storeUtil';
import { genUuid } from '@/c-utils/common';
import { subscribeWithSelector } from 'zustand/middleware';

import { removeParamFromUrl } from '@/c-utils/urlUtils';
import i18n from '@/i18n';
import { UserStoreState } from '@/c-types/store';


// Helper function to register as guest user
const registerAsGuest = async (): Promise<string> => {
  const tokenData = tokenTool.get();
  if (tokenData.faked) {
    return tokenData.token;
  }
  const res = await registerTmp({ temp_id: genUuid() });
  const token = res.token;
  tokenTool.set({ token, faked: true });
  return token;
};

export const useUserStore = create<UserStoreState, [["zustand/subscribeWithSelector", never]]>(
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
      set(() => ({
        userInfo,
      }));

      if (userInfo.language) {
        i18n.changeLanguage(userInfo.language);
      }

      get()._updateUserStatus();
    },

    // Public API: Logout user
    logout: async (reload = true) => {
      await registerAsGuest();
      set(() => ({
        userInfo: null,
      }));

      get()._updateUserStatus();

      if (reload) {
        const url = removeParamFromUrl(window.location.href, ['code', 'state']);
        window.location.assign(url);
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

      // If no token, register as guest
      if (!tokenData.token) {
        await registerAsGuest();
        set(() => ({
          userInfo: null,
        }));
        get()._updateUserStatus();
        return;
      }

      // If already has token, try to get user info
      try {
        const res = await getUserInfo();
        const userInfo = res;

        // Determine if user is authenticated based on mobile number or email
        const isAuthenticated = !!(userInfo.mobile || userInfo.email);
        tokenTool.set({ token: tokenData.token, faked: !isAuthenticated });

        set(() => ({
          userInfo,
        }));

        if (userInfo.language) {
          i18n.changeLanguage(userInfo.language);
        }
      } catch (err) {
        // @ts-expect-error EXPECT
        // Only reset to guest if it's a clear authentication error (not network or server issues)
        if ((err.status === 403) || (err.code === 1005) || (err.code === 1001)) {
          await registerAsGuest();
          set(() => ({
            userInfo: null,
          }));
        } else {
          // For other errors (network, server errors), preserve existing token state
          // but still update the status based on token data
          console.warn('Failed to fetch user info, but preserving login state:', err);
        }
      }

        get()._updateUserStatus();
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
    updateUserInfo: (userInfo) => {
      set((state) => ({
        userInfo: {
          ...state.userInfo,
          ...userInfo,
        }
      }));
    },

    // Public API: Refresh user information from server
    refreshUserInfo: async () => {
      const res = await getUserInfo();
      set(() => ({
        userInfo: {
          ...res
        }
      }));

      if (res.language) {
        i18n.changeLanguage(res.language);
      }
    },
  }))
);
