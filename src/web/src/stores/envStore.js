import { create } from 'zustand';

export const useEnvStore = create((set) => ({
  courseId: process.env.REACT_APP_COURSE_ID,
  updateCourseId: (courseId) => set({ courseId }),
  appId: process.env.REACT_APP_APP_ID,
  updateAppId: (appId) => set({ appId }),
  alwaysShowLessonTree: process.env.REACT_APP_ALWAYS_SHOW_LESSON_TREE || false,
  updateAlwaysShowLessonTree: (alwaysShowLessonTree) => set({ alwaysShowLessonTree }),
  umamiWebsiteId: process.env.REACT_APP_UMAMI_WEBSITE_ID,
  updateUmamiWebsiteId: (umamiWebsiteId) => set({ umamiWebsiteId }),
  umamiScriptSrc: process.env.REACT_APP_UMAMI_SCRIPT_SRC,
  updateUmamiScriptSrc: (umamiScriptSrc) => set({ umamiScriptSrc }),
  eruda: process.env.REACT_APP_ERUDA || false,
  updateEruda: (eruda) => set({ eruda }),
  baseURL: process.env.REACT_APP_BASEURL,
  updateBaseURL: (baseURL) => set({ baseURL }),
}));
