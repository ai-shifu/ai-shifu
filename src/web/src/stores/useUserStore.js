import { create } from 'zustand';
import { getUserInfo, registerTmp } from 'Api/user.js';
import { userInfoStore, tokenTool } from 'Service/storeUtil.js';
import { genUuid } from 'Utils/common.js';
import { verifySmsCode } from 'Api/user.js';
import { subscribeWithSelector } from 'zustand/middleware';
import i18n from '../i18n.js';
export const useUserStore = create(
  subscribeWithSelector((set) => ({
    hasLogin: false,
    userInfo: null,

    login: async ({ mobile, smsCode }) => {
      const res = await verifySmsCode({ mobile, sms_code: smsCode });
      const { userInfo, token } = res.data;
      tokenTool.set({ token, faked: false });

      set(() => ({
        hasLogin: true,
        userInfo,
      }));
      i18n.changeLanguage(userInfo.language);

    },

    // 通过接口检测登录状态
    checkLogin: async () => {
      if (!tokenTool.get().token) {
        const res = await registerTmp({ temp_id: genUuid() });
        const token = res.data.token;
        tokenTool.set({ token, faked: true });
        set(() => ({
          hasLogin: false,
          userInfo: null,
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
            hasLogin: true,
            userInfo,
          }));
        } else {
          tokenTool.set({ token: tokenTool.get().token, faked: true });
          set(() => ({
            hasLogin: false,
            userInfo: userInfo,
          }));
        }
        i18n.changeLanguage(userInfo.language);
      } catch (err) {
        if ((err.status && err.status === 403) || (err.code && err.code === 1005) || (err.code && err.code === 1001)) {
          const res = await registerTmp({ temp_id: genUuid() });
          const token = res.data.token;
          await tokenTool.set({ token, faked: true });

          set(() => ({
            hasLogin: false,
            userInfo: null,
          }));
        }
      }
    },

    logout: async () => {
      const res = await registerTmp({ temp_id: genUuid() });
      const token = res.data.token;
      tokenTool.set({ token, faked: true });
      userInfoStore.remove();

      set(() => {
        return {
          hasLogin: false,
          userInfo: null,
        };
      });
    },

    // 更新用户信息
    updateUserInfo: (userInfo) => {
      set((state) => {
        return {
          userInfo: {
            ...state.userInfo,
            ...userInfo,
          }
        };
      });
    },

    refreshUserInfo: async () => {
      const res = await getUserInfo();
      set(() => ({
        userInfo: {
          ...res.data
        }
      }));
      await userInfoStore.set(res.data);
      i18n.changeLanguage(res.data.language);

    }
  }))
);
