import { UserInfo } from './index';

export interface LegalUrls {
  agreement: {
    'zh-CN': string;
    'en-US': string;
  };
  privacy: {
    'zh-CN': string;
    'en-US': string;
  };
}

export interface EnvStoreState {
  courseId: string;
  defaultLlmModel: string;
  appId: string;
  alwaysShowLessonTree: string;
  umamiWebsiteId: string;
  umamiScriptSrc: string;
  eruda: string;
  baseURL: string;
  logoHorizontal: string;
  logoVertical: string;
  logoWideUrl: string;
  logoSquareUrl: string;
  faviconUrl: string;
  enableWxcode: string;
  homeUrl: string;
  currencySymbol: string;
  stripePublishableKey: string;
  stripeEnabled: string;
  payOrderExpireSeconds: number;
  paymentChannels: string[];
  loginMethodsEnabled: string[];
  defaultLoginMethod: string;
  legalUrls: LegalUrls;
  runtimeConfigLoaded: boolean;
  updateCourseId: (courseId: string) => Promise<void>;
  updateDefaultLlmModel: (model: string) => Promise<void>;
  updateAppId: (appId: string) => Promise<void>;
  updateAlwaysShowLessonTree: (value: string) => Promise<void>;
  updateUmamiWebsiteId: (id: string) => Promise<void>;
  updateUmamiScriptSrc: (src: string) => Promise<void>;
  updateEruda: (value: string) => Promise<void>;
  updateBaseURL: (url: string) => Promise<void>;
  updateLogoHorizontal: (logo: string) => Promise<void>;
  updateLogoVertical: (logo: string) => Promise<void>;
  updateLogoWideUrl: (logo: string) => Promise<void>;
  updateLogoSquareUrl: (logo: string) => Promise<void>;
  updateFaviconUrl: (icon: string) => Promise<void>;
  updateEnableWxcode: (value: string) => Promise<void>;
  updateHomeUrl: (url: string) => Promise<void>;
  updateCurrencySymbol: (symbol: string) => Promise<void>;
  updateStripePublishableKey: (key: string) => Promise<void>;
  updateStripeEnabled: (value: string) => Promise<void>;
  updatePayOrderExpireSeconds: (seconds: number) => Promise<void>;
  updatePaymentChannels: (channels: string[]) => Promise<void>;
  updateLoginMethodsEnabled: (methods: string[]) => Promise<void>;
  updateDefaultLoginMethod: (method: string) => Promise<void>;
  updateLegalUrls: (legalUrls: LegalUrls) => Promise<void>;
  setRuntimeConfigLoaded: (loaded: boolean) => void;
}

export interface SystemStoreState {
  language: string;
  channel: string;
  wechatCode: string;
  showVip: boolean;
  previewMode: boolean;
  skip: boolean;
  learningMode: 'listen' | 'read';
  updateLanguage: (language: string) => void;
  updateChannel: (channel: string) => void;
  updateWechatCode: (code: string) => void;
  setShowVip: (show: boolean) => void;
  updatePreviewMode: (mode: boolean) => void;
  updateSkip: (skip: boolean) => void;
  updateLearningMode: (mode: 'listen' | 'read') => void;
}

export interface CourseStoreState {
  courseName: string;
  courseAvatar: string;
  updateCourseAvatar: (avatar: string) => void;
  updateCourseName: (name: string) => void;
  lessonId: string | undefined;
  updateLessonId: (id: string) => void;
  chapterId: string;
  updateChapterId: (id: string) => void;
  purchased: boolean;
  changePurchased: (purchased: boolean) => void;
  resetedChapterId: string | null;
  resetedLessonId: string;
  updateResetedChapterId: (id: string) => void;
  updateResetedLessonId: (id: string) => void;
  resetChapter: (id: string) => Promise<void>;
  payModalOpen: boolean;
  payModalState: {
    type: string;
    payload: Record<string, any>;
  };
  openPayModal: (options?: {
    type?: string;
    payload?: Record<string, any>;
  }) => void;
  closePayModal: () => void;
  setPayModalState: (state?: {
    type?: string;
    payload?: Record<string, any>;
  }) => void;
  payModalResult: 'ok' | 'cancel' | null;
  setPayModalResult: (result: 'ok' | 'cancel' | null) => void;
}

export interface UserStoreState {
  userInfo: UserInfo | null;
  isGuest: boolean;
  isLoggedIn: boolean;
  isInitialized: boolean;
  // Internal state
  _initializingPromise: Promise<void> | null;
  // Internal methods
  _updateUserStatus: () => void;
  // Public API
  getToken: () => string;
  initUser: () => Promise<void>;
  login: (userInfo: any, token: string) => Promise<void>;
  logout: (reload?: boolean) => Promise<void>;
  updateUserInfo: (info: Partial<UserInfo>) => void;
  refreshUserInfo: () => Promise<void>;
  ensureGuestToken: () => Promise<void>;
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
