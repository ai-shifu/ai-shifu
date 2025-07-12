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
  await tokenTool.set({ token, faked: true });
  return token;
};

export const useUserStore = create<UserStoreState, [["zustand/subscribeWithSelector", never]]>(
  subscribeWithSelector((set, get) => ({
    userInfo: null,
    isGuest: false,
    isLoggedIn: false,
    isInitialized: false,

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
      await tokenTool.set({ token, faked: false });
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

        // Determine if user is authenticated based on mobile number
        const isAuthenticated = !!userInfo.mobile;
        await tokenTool.set({ token: tokenData.token, faked: !isAuthenticated });

        set(() => ({
          userInfo,
        }));

        if (userInfo.language) {
          i18n.changeLanguage(userInfo.language);
        }
      } catch (err) {
        // @ts-expect-error EXPECT
        if ((err.status === 403) || (err.code === 1005) || (err.code === 1001)) {
          await registerAsGuest();
          set(() => ({
            userInfo: null,
          }));
        }
      }

      get()._updateUserStatus();
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