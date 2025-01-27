import { create } from 'zustand';
import { isMobile, isAndroid, isIOS, isMacOs, isWindows } from 'react-device-detect';
import { calcFrameLayout } from '@constants/uiConstants.js';

export const useUiLayoutStore = create((set) => ({
  frameLayout: calcFrameLayout('#root'),
  inMobile: isMobile,
  inWeixin: isAndroid,
  inWindows: isWindows,
  inMacOs: isMacOs,
  inIos: isIOS,
  updateFrameLayout: (frameLayout) => set(() => ({ frameLayout })),
  checkMobileEnv: () => set(() => {
    return {
      inMobile: isMobile,
      isWeixin: /MicroMessenger/i.test(window.navigator.userAgent),
    };
  }),
}));
