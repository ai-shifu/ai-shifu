import { UserInfo } from './index';

export interface EnvStoreState {
  courseId: string;
  appId: string;
  alwaysShowLessonTree: string;
  umamiWebsiteId: string;
  umamiScriptSrc: string;
  eruda: string;
  baseURL: string;
  logoHorizontal: string;
  logoVertical: string;
  enableWxcode: string;
  siteUrl: string;
  updateCourseId: (courseId: string) => Promise<void>;
  updateAppId: (appId: string) => Promise<void>;
  updateAlwaysShowLessonTree: (value: string) => Promise<void>;
  updateUmamiWebsiteId: (id: string) => Promise<void>;
  updateUmamiScriptSrc: (src: string) => Promise<void>;
  updateEruda: (value: string) => Promise<void>;
  updateBaseURL: (url: string) => Promise<void>;
  updateLogoHorizontal: (logo: string) => Promise<void>;
  updateLogoVertical: (logo: string) => Promise<void>;
  updateEnableWxcode: (value: string) => Promise<void>;
  updateSiteUrl: (url: string) => Promise<void>;
}

export interface SystemStoreState {
  language: string;
  channel: string;
  wechatCode: string;
  showVip: boolean;
  previewMode: boolean;
  skip: boolean;
  updateLanguage: (language: string) => void;
  updateChannel: (channel: string) => void;
  updateWechatCode: (code: string) => void;
  setShowVip: (show: boolean) => void;
  updatePreviewMode: (mode: boolean) => void;
  updateSkip: (skip: boolean) => void;
}

export interface CourseStoreState {
  courseName: string;
  updateCourseName: (name: string) => void;
  lessonId: string | null;
  updateLessonId: (id: string) => void;
  chapterId: string;
  updateChapterId: (id: string) => void;
  purchased: boolean;
  changePurchased: (purchased: boolean) => void;
  resetedChapterId: string | null;
  updateResetedChapterId: (id: string) => void;
  resetChapter: (id: string) => Promise<void>;
}

export interface UserStoreState {
  userInfo: UserInfo | null;
  hasLogin: boolean;
  hasCheckLogin: boolean;
  login: (params: { mobile: string; smsCode: string }) => Promise<void>;
  checkLogin: () => void;
  checkLoginForce: () => Promise<void>;
  logout: (reload?: boolean) => Promise<void>;
  updateUserInfo: (info: Partial<UserInfo>) => void;
  refreshUserInfo: () => Promise<void>;
  updateHasCheckLogin: (hasCheckLogin: boolean) => void;
}

export interface UiLayoutStoreState {
  frameLayout: any;
  inMobile: boolean;
  inWeixin: boolean;
  inWindows: boolean;
  inMacOs: boolean;
  inIos: boolean;
  updateFrameLayout: (frameLayout: any) => void;
  checkMobileEnv: () => void;
  isWeixin?: boolean;
}
