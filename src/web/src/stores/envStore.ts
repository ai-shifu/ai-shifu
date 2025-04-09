import { create } from 'zustand';
import { EnvStoreState } from '../types/store';

const env = {
  REACT_APP_COURSE_ID: '',
  REACT_APP_APP_ID: '',
  REACT_APP_ALWAYS_SHOW_LESSON_TREE: 'false',
  REACT_APP_UMAMI_WEBSITE_ID: '',
  REACT_APP_UMAMI_SCRIPT_SRC: '',
  REACT_APP_ERUDA: 'false',
  REACT_APP_BASEURL: '',
  REACT_APP_LOGO_HORIZONTAL: '',
  REACT_APP_LOGO_VERTICAL: '',
  REACT_APP_ENABLE_WXCODE: 'false',
  REACT_APP_SITE_URL: '/',
};

export const useEnvStore = create<EnvStoreState>((set) => ({
  courseId: env.REACT_APP_COURSE_ID,
  updateCourseId: async (courseId: string) => set({ courseId }),
  appId: env.REACT_APP_APP_ID,
  updateAppId: async (appId: string) => set({ appId }),
  alwaysShowLessonTree: env.REACT_APP_ALWAYS_SHOW_LESSON_TREE || 'false',
  updateAlwaysShowLessonTree: async (alwaysShowLessonTree: string) => set({ alwaysShowLessonTree }),
  umamiWebsiteId: env.REACT_APP_UMAMI_WEBSITE_ID,
  updateUmamiWebsiteId: async (umamiWebsiteId: string) => set({ umamiWebsiteId }),
  umamiScriptSrc: env.REACT_APP_UMAMI_SCRIPT_SRC,
  updateUmamiScriptSrc: async (umamiScriptSrc: string) => set({ umamiScriptSrc }),
  eruda: env.REACT_APP_ERUDA || 'false',
  updateEruda: async (eruda: string) => set({ eruda }),
  baseURL: env.REACT_APP_BASEURL,
  updateBaseURL: async (baseURL: string) => set({ baseURL }),
  logoHorizontal: env.REACT_APP_LOGO_HORIZONTAL,
  updateLogoHorizontal: async (logoHorizontal: string) => set({ logoHorizontal }),
  logoVertical: env.REACT_APP_LOGO_VERTICAL,
  updateLogoVertical: async (logoVertical: string) => set({ logoVertical }),
  enableWxcode: env.REACT_APP_ENABLE_WXCODE || 'false',
  updateEnableWxcode: async (enableWxcode: string) => set({ enableWxcode }),
  siteUrl: env.REACT_APP_SITE_URL || '/',
  updateSiteUrl: async (siteUrl: string) => set({ siteUrl }),
}));
