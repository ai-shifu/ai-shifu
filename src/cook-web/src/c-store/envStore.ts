import { create } from 'zustand';
import { EnvStoreState } from '@/c-types/store';
import { environment } from '@/config/environment';

export const useEnvStore = create<EnvStoreState>((set) => ({
  courseId: environment.courseId,
  updateCourseId: async (courseId: string) => set({ courseId }),
  appId: environment.wechatAppId,
  updateAppId: async (appId: string) => set({ appId }),
  alwaysShowLessonTree: environment.alwaysShowLessonTree.toString(),
  updateAlwaysShowLessonTree: async (alwaysShowLessonTree: string) => set({ alwaysShowLessonTree }),
  umamiWebsiteId: environment.umamiWebsiteId,
  updateUmamiWebsiteId: async (umamiWebsiteId: string) => set({ umamiWebsiteId }),
  umamiScriptSrc: environment.umamiScriptSrc,
  updateUmamiScriptSrc: async (umamiScriptSrc: string) => set({ umamiScriptSrc }),
  eruda: environment.enableEruda.toString(),
  updateEruda: async (eruda: string) => set({ eruda }),
  baseURL: environment.apiBaseUrl,
  updateBaseURL: async (baseURL: string) => set({ baseURL }),
  logoHorizontal: environment.logoHorizontal,
  updateLogoHorizontal: async (logoHorizontal: string) => set({ logoHorizontal }),
  logoVertical: environment.logoVertical,
  updateLogoVertical: async (logoVertical: string) => set({ logoVertical }),
  enableWxcode: environment.enableWechatCode.toString(),
  updateEnableWxcode: async (enableWxcode: string) => set({ enableWxcode }),
  siteUrl: environment.apiBaseUrl,
  updateSiteUrl: async (siteUrl: string) => set({ siteUrl }),
}));
