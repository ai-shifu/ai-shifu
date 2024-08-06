import { create } from 'zustand';
import { getUserInfo, registerTmp } from 'Api/user.js';
import { userInfoStore, tokenTool } from 'Service/storeUtil.js';
import { genUuid } from 'Utils/common.js';
import { verifySmsCode } from 'Api/user.js';

export const useUserStore = create((set) => ({
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
      return
    }

    if (userInfoStore.get()) {
      set(() => ({
        userInfo: userInfoStore.get(),
      }));
    }

    try {
      const res = await getUserInfo();
      const userInfo = res.data;

      tokenTool.set({ token: tokenTool.get().token, faked: false });
      userInfoStore.set(userInfo);
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
    } catch (err) {
      if ((err.status && err.status === 403) || (err.code && err.code === 1005) || (err.code && err.code === 1001)) {
        const res = await registerTmp({ temp_id: genUuid() });
        const token = res.data.token;
        tokenTool.set({ token, faked: true });

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
    })
  },

  // 更新用户信息
  updateUserInfo: (userInfo) => {
    set((state) => {
      return {
        userInfo: {
          ...state.userInfo,
          ...userInfo,
        }
      }
    });
  },

  refreshUserInfo: async () => {
    const res = await getUserInfo();
    const userInfo = res.data;
  }
}));
