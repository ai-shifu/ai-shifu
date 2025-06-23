import { create } from 'zustand';
import { EnvStoreState } from '@/c-types/store';

const env = {
  NEXT_PUBLIC_COURSE_ID: process.env.NEXT_PUBLIC_COURSE_ID,
  NEXT_PUBLIC_APP_ID: process.env.NEXT_PUBLIC_APP_ID,
  NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE: process.env.NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE || 'false',
  NEXT_PUBLIC_UMAMI_WEBSITE_ID: process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID,
  NEXT_PUBLIC_UMAMI_SCRIPT_SRC: process.env.NEXT_PUBLIC_UMAMI_SCRIPT_SRC,
  NEXT_PUBLIC_ERUDA: process.env.NEXT_PUBLIC_ERUDA || 'false',
  NEXT_PUBLIC_BASEURL: process.env.NEXT_PUBLIC_BASEURL,
  NEXT_PUBLIC_LOGO_HORIZONTAL: process.env.NEXT_PUBLIC_LOGO_HORIZONTAL,
  NEXT_PUBLIC_LOGO_VERTICAL: process.env.NEXT_PUBLIC_LOGO_HORIZONTAL,
  NEXT_PUBLIC_ENABLE_WXCODE: process.env.NEXT_PUBLIC_ENABLE_WXCODE,
  NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_ENABLE_WXCODE,
};

export const useEnvStore = create<EnvStoreState>((set) => ({
  courseId: env.NEXT_PUBLIC_COURSE_ID,
  updateCourseId: async (courseId: string) => set({ courseId }),
  appId: env.NEXT_PUBLIC_APP_ID,
  updateAppId: async (appId: string) => set({ appId }),
  alwaysShowLessonTree: env.NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE,
  updateAlwaysShowLessonTree: async (alwaysShowLessonTree: string) => set({ alwaysShowLessonTree }),
  umamiWebsiteId: env.NEXT_PUBLIC_UMAMI_WEBSITE_ID,
  updateUmamiWebsiteId: async (umamiWebsiteId: string) => set({ umamiWebsiteId }),
  umamiScriptSrc: env.NEXT_PUBLIC_UMAMI_SCRIPT_SRC,
  updateUmamiScriptSrc: async (umamiScriptSrc: string) => set({ umamiScriptSrc }),
  eruda: env.NEXT_PUBLIC_ERUDA,
  updateEruda: async (eruda: string) => set({ eruda }),
  baseURL: env.NEXT_PUBLIC_BASEURL,
  updateBaseURL: async (baseURL: string) => set({ baseURL }),
  logoHorizontal: env.NEXT_PUBLIC_LOGO_HORIZONTAL,
  updateLogoHorizontal: async (logoHorizontal: string) => set({ logoHorizontal }),
  logoVertical: env.NEXT_PUBLIC_LOGO_VERTICAL,
  updateLogoVertical: async (logoVertical: string) => set({ logoVertical }),
  enableWxcode: env.NEXT_PUBLIC_ENABLE_WXCODE || 'false',
  updateEnableWxcode: async (enableWxcode: string) => set({ enableWxcode }),
  siteUrl: env.NEXT_PUBLIC_SITE_URL,
  updateSiteUrl: async (siteUrl: string) => set({ siteUrl }),
}));
