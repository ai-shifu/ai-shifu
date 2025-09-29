import { create } from 'zustand';
import { EnvStoreState } from '../types/store';

// 获取URL中的课程ID，优先使用URL参数
const getCourseIdFromUrl = (): string | undefined => {
  if (typeof window === 'undefined') return undefined;
  const path = window.location.pathname;
  const match = path.match(/^\/c\/([^\/]+)$/);
  return match ? match[1] : undefined;
};

const env = {
  REACT_APP_COURSE_ID: process.env.REACT_APP_COURSE_ID,
  REACT_APP_APP_ID: process.env.REACT_APP_APP_ID,
  REACT_APP_ALWAYS_SHOW_LESSON_TREE: process.env.REACT_APP_ALWAYS_SHOW_LESSON_TREE || 'false',
  REACT_APP_UMAMI_WEBSITE_ID: process.env.REACT_APP_UMAMI_WEBSITE_ID,
  REACT_APP_UMAMI_SCRIPT_SRC: process.env.REACT_APP_UMAMI_SCRIPT_SRC,
  REACT_APP_ERUDA: process.env.REACT_APP_ERUDA || 'false',
  REACT_APP_BASEURL: process.env.REACT_APP_BASEURL,
  REACT_APP_LOGO_HORIZONTAL: process.env.REACT_APP_LOGO_HORIZONTAL,
  REACT_APP_LOGO_VERTICAL: process.env.REACT_APP_LOGO_HORIZONTAL,
  REACT_APP_ENABLE_WXCODE: process.env.REACT_APP_ENABLE_WXCODE,
  REACT_APP_SITE_URL: process.env.REACT_APP_ENABLE_WXCODE,
};

export const useEnvStore = create<EnvStoreState>((set) => {
  const store = {
    courseId: getCourseIdFromUrl() || env.REACT_APP_COURSE_ID,
    updateCourseId: async (courseId: string) => set({ courseId }),
    appId: env.REACT_APP_APP_ID,
    updateAppId: async (appId: string) => set({ appId }),
    alwaysShowLessonTree: env.REACT_APP_ALWAYS_SHOW_LESSON_TREE,
    updateAlwaysShowLessonTree: async (alwaysShowLessonTree: string) => set({ alwaysShowLessonTree }),
    umamiWebsiteId: env.REACT_APP_UMAMI_WEBSITE_ID,
    updateUmamiWebsiteId: async (umamiWebsiteId: string) => set({ umamiWebsiteId }),
    umamiScriptSrc: env.REACT_APP_UMAMI_SCRIPT_SRC,
    updateUmamiScriptSrc: async (umamiScriptSrc: string) => set({ umamiScriptSrc }),
    eruda: env.REACT_APP_ERUDA,
    updateEruda: async (eruda: string) => set({ eruda }),
    baseURL: env.REACT_APP_BASEURL,
    updateBaseURL: async (baseURL: string) => set({ baseURL }),
    logoHorizontal: env.REACT_APP_LOGO_HORIZONTAL,
    updateLogoHorizontal: async (logoHorizontal: string) => set({ logoHorizontal }),
    logoVertical: env.REACT_APP_LOGO_VERTICAL,
    updateLogoVertical: async (logoVertical: string) => set({ logoVertical }),
    enableWxcode: env.REACT_APP_ENABLE_WXCODE || 'false',
    updateEnableWxcode: async (enableWxcode: string) => set({ enableWxcode }),
    siteUrl: env.REACT_APP_SITE_URL,
    updateSiteUrl: async (siteUrl: string) => set({ siteUrl }),
  };

  // 异步加载环境变量，只更新courseId
  fetch('/config/env', {
    method: 'POST',
    headers: { 'Cache-Control': 'no-cache' }
  })
  .then(response => response.json())
  .then(data => {
    const urlCourseId = getCourseIdFromUrl();
    set({ courseId: urlCourseId || data.REACT_APP_COURSE_ID });
  })
  .catch(() => {
  });

  return store;
});
