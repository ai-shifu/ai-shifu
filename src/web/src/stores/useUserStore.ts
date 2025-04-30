import { create } from 'zustand';
import { getUserInfo, registerTmp } from 'Api/user';
import { userInfoStore, tokenTool } from 'Service/storeUtil';
import { genUuid } from 'Utils/common';
import { verifySmsCode } from 'Api/user';
import { subscribeWithSelector } from 'zustand/middleware';

import { removeParamFromUrl } from 'Utils/urlUtils';
import i18n from '../i18n';
import { UserStoreState } from '../types/store';
import { useEnvStore } from './envStore';

export const useUserStore = create<
  UserStoreState,
  [['zustand/subscribeWithSelector', never]]
>(
  subscribeWithSelector((set) => ({
    hasCheckLogin: false,
    hasLogin: false,
    userInfo: null,
    login: async ({ mobile, smsCode }) => {
      const courseId = useEnvStore.getState().courseId;
      const res = await verifySmsCode({
        mobile,
        sms_code: smsCode,
        course_id: courseId,
      });
      const { userInfo, token } = res.data;
      await tokenTool.set({ token, faked: false });

      set(() => ({
        hasLogin: true,
        userInfo,
      }));
      i18n.changeLanguage(userInfo.language);
    },

    checkLoginForce: async () => {
      if (!tokenTool.get().token) {
        const res = await registerTmp({ temp_id: genUuid() });
        const token = res.data.token;
        await tokenTool.set({ token, faked: true });
        set(() => ({
          hasLogin: false,
          userInfo: null,
          hasCheckLogin: true,
        }));
        return;
      }

      if (userInfoStore.get()) {
        set(() => ({
          userInfo: userInfoStore.get(),
        }));
      }

      try {
        const res = await getUserInfo();
        const userInfo = res.data;
        await tokenTool.set({ token: tokenTool.get().token, faked: false });
        await userInfoStore.set(userInfo);
        if (userInfo.mobile) {
          set(() => ({
            hasCheckLogin: true,
            hasLogin: true,
            userInfo,
          }));
        } else {
          await tokenTool.set({ token: tokenTool.get().token, faked: true });
          set(() => ({
            hasCheckLogin: true,
            hasLogin: false,
            userInfo: userInfo,
          }));
        }
        i18n.changeLanguage(userInfo.language);
      } catch (err) {
        if (
          (err.status && err.status === 403) ||
          (err.code && err.code === 1005) ||
          (err.code && err.code === 1001)
        ) {
          const res = await registerTmp({ temp_id: genUuid() });
          const token = res.data.token;
          await tokenTool.set({ token, faked: true });

          set(() => ({
            hasCheckLogin: true,
            hasLogin: false,
            userInfo: null,
          }));
        }
      }
    },

    // 通过接口检测登录状态
    checkLogin: () => {
      const state = useUserStore.getState();
      if (state.hasCheckLogin) {
        return;
      }
      state.checkLoginForce();
    },

    logout: async (reload = true) => {
      const res = await registerTmp({ temp_id: genUuid() });
      const token = res.data.token;
      await tokenTool.set({ token, faked: true });
      await userInfoStore.remove();

      set(() => {
        return {
          hasLogin: false,
          userInfo: null,
        };
      });

      if (reload) {
        const url = removeParamFromUrl(window.location.href, ['code', 'state']);
        window.location.assign(url);
      }
    },

    // 更新用户信息
    updateUserInfo: (userInfo) => {
      set((state) => {
        return {
          userInfo: {
            ...state.userInfo,
            ...userInfo,
          },
        };
      });
    },

    refreshUserInfo: async () => {
      const res = await getUserInfo();
      set(() => ({
        userInfo: {
          ...res.data,
        },
      }));
      await userInfoStore.set(res.data);
      i18n.changeLanguage(res.data.language);
    },

    updateHasCheckLogin: (hasCheckLogin) => set(() => ({ hasCheckLogin })),
  })),
);
