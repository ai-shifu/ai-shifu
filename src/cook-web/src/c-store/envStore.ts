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
  NEXT_PUBLIC_LOGO_VERTICAL: process.env.NEXT_PUBLIC_LOGO_VERTICAL,
  NEXT_PUBLIC_ENABLE_WXCODE: process.env.NEXT_PUBLIC_ENABLE_WXCODE,
  NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
};

export const useEnvStore = create<EnvStoreState>((set) => ({
  // @ts-expect-error EXPECT
  courseId: env.NEXT_PUBLIC_COURSE_ID,
  updateCourseId: async (courseId: string) => set({ courseId }),
  // @ts-expect-error EXPECT
  appId: env.NEXT_PUBLIC_APP_ID,
  updateAppId: async (appId: string) => set({ appId }),
  alwaysShowLessonTree: env.NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE,
  updateAlwaysShowLessonTree: async (alwaysShowLessonTree: string) => set({ alwaysShowLessonTree }),
  // @ts-expect-error EXPECT
  umamiWebsiteId: env.NEXT_PUBLIC_UMAMI_WEBSITE_ID,
  updateUmamiWebsiteId: async (umamiWebsiteId: string) => set({ umamiWebsiteId }),
  // @ts-expect-error EXPECT
  umamiScriptSrc: env.NEXT_PUBLIC_UMAMI_SCRIPT_SRC,
  updateUmamiScriptSrc: async (umamiScriptSrc: string) => set({ umamiScriptSrc }),
  eruda: env.NEXT_PUBLIC_ERUDA,
  updateEruda: async (eruda: string) => set({ eruda }),
  // @ts-expect-error EXPECT
  baseURL: env.NEXT_PUBLIC_BASEURL,
  updateBaseURL: async (baseURL: string) => set({ baseURL }),
  // @ts-expect-error EXPECT
  logoHorizontal: env.NEXT_PUBLIC_LOGO_HORIZONTAL,
  updateLogoHorizontal: async (logoHorizontal: string) => set({ logoHorizontal }),
  // @ts-expect-error EXPECT
  logoVertical: env.NEXT_PUBLIC_LOGO_VERTICAL,
  updateLogoVertical: async (logoVertical: string) => set({ logoVertical }),
  enableWxcode: env.NEXT_PUBLIC_ENABLE_WXCODE || 'false',
  updateEnableWxcode: async (enableWxcode: string) => set({ enableWxcode }),
  // @ts-expect-error EXPECT
  siteUrl: env.NEXT_PUBLIC_SITE_URL,
  updateSiteUrl: async (siteUrl: string) => set({ siteUrl }),
}));
