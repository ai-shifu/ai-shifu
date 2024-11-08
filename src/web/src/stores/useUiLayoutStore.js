import { create } from 'zustand';
import { isMobile } from 'react-device-detect';
import { calcFrameLayout } from '@constants/uiConstants.js';

export const useUiLayoutStore = create((set) => ({
  frameLayout: calcFrameLayout('#root'),
  inMobile: isMobile,
  inWeixin: false,
  updateFrameLayout: (frameLayout) => set(() => ({ frameLayout })),
  checkMobileEnv: () => set(() => {
    return {
      inMobile: isMobile,
      isWeixin: /MicroMessenger/i.test(window.navigator.userAgent),
    };
  }),
}));
