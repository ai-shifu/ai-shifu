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
  // Always fetch a fresh guest token to avoid expiration issues
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
      set(() => ({
        userInfo,
      }));

      // Let i18next handle the language and its fallback mechanism
      i18n.changeLanguage(userInfo.language);

      get()._updateUserStatus();
    },

    // Public API: Logout user
    logout: async (reload = true) => {
      // BUGFIX: 防止退出登录时页面双重加载问题
      // 问题：logout触发页面刷新后，某些API请求返回认证错误，导致request.ts再次触发页面跳转
      // 解决：设置全局标志，让request.ts在logout过程中跳过自动跳转逻辑
      // 相关文件：src/lib/request.ts
      if (typeof window !== 'undefined') {
        window.__IS_LOGGING_OUT__ = true;
      }

      await registerAsGuest();
      set(() => ({
        userInfo: null,
      }));

      get()._updateUserStatus();

      if (reload) {
        // OPTIMIZATION: 使用replace而不是assign，避免在浏览器历史中创建重复记录
        // 这样用户点击后退按钮时不会回到"退出登录"的中间状态
        const url = removeParamFromUrl(window.location.href, ['code', 'state']);
        window.location.replace(url);
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
          // Let i18next handle the language and its fallback mechanism
          i18n.changeLanguage(userInfo.language);
        } catch (err) {
          // @ts-expect-error EXPECT
          // Only reset to guest if it's a clear authentication error (not network or server issues)
          if (err.status === 403 || err.code === 1005 || err.code === 1001) {
            await registerAsGuest();
            set(() => ({
              userInfo: null,
            }));
          } else {
            // For other errors (network, server errors), preserve existing token state
            // but still update the status based on token data
            console.warn(
              'Failed to fetch user info, but preserving login state:',
              err,
            );
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
  })),
);
