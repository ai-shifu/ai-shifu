import { create } from 'zustand';
import { EnvStoreState } from '@/c-types/store';
import { environment } from '@/config/environment';

export const useEnvStore = create<EnvStoreState>(set => ({
  courseId: environment.courseId,
  updateCourseId: async (courseId: string) => set({ courseId }),
  defaultLlmModel: environment.defaultLlmModel,
  updateDefaultLlmModel: async (defaultLlmModel: string) =>
    set({ defaultLlmModel }),
  appId: environment.wechatAppId,
  updateAppId: async (appId: string) => set({ appId }),
  alwaysShowLessonTree: environment.alwaysShowLessonTree.toString(),
  updateAlwaysShowLessonTree: async (alwaysShowLessonTree: string) =>
    set({ alwaysShowLessonTree }),
  umamiWebsiteId: environment.umamiWebsiteId,
  updateUmamiWebsiteId: async (umamiWebsiteId: string) =>
    set({ umamiWebsiteId }),
  umamiScriptSrc: environment.umamiScriptSrc,
  updateUmamiScriptSrc: async (umamiScriptSrc: string) =>
    set({ umamiScriptSrc }),
  eruda: environment.enableEruda.toString(),
  updateEruda: async (eruda: string) => set({ eruda }),
  baseURL: environment.apiBaseUrl.replace(/\/+$/, ''),
  updateBaseURL: async (baseURL: string) =>
    set({ baseURL: baseURL.replace(/\/+$/, '') }),
  logoHorizontal: environment.logoHorizontal,
  updateLogoHorizontal: async (logoHorizontal: string) =>
    set({ logoHorizontal }),
  logoVertical: environment.logoVertical,
  updateLogoVertical: async (logoVertical: string) => set({ logoVertical }),
  logoWideUrl: environment.logoWideUrl,
  updateLogoWideUrl: async (logoWideUrl: string) => set({ logoWideUrl }),
  logoSquareUrl: environment.logoSquareUrl,
  updateLogoSquareUrl: async (logoSquareUrl: string) => set({ logoSquareUrl }),
  faviconUrl: environment.faviconUrl,
  updateFaviconUrl: async (faviconUrl: string) => set({ faviconUrl }),
  enableWxcode: environment.enableWechatCode.toString(),
  updateEnableWxcode: async (enableWxcode: string) => set({ enableWxcode }),
  homeUrl: environment.homeUrl,
  updateHomeUrl: async (homeUrl: string) => set({ homeUrl }),
  currencySymbol: environment.currencySymbol,
  updateCurrencySymbol: async (currencySymbol: string) =>
    set({ currencySymbol }),
  stripePublishableKey: environment.stripePublishableKey,
  updateStripePublishableKey: async (stripePublishableKey: string) =>
    set({ stripePublishableKey }),
  stripeEnabled: environment.stripeEnabled.toString(),
  updateStripeEnabled: async (stripeEnabled: string) => set({ stripeEnabled }),
  paymentChannels: environment.paymentChannels,
  updatePaymentChannels: async (paymentChannels: string[]) =>
    set({ paymentChannels }),
  loginMethodsEnabled: environment.loginMethodsEnabled,
  updateLoginMethodsEnabled: async (loginMethodsEnabled: string[]) =>
    set({ loginMethodsEnabled }),
  defaultLoginMethod: environment.defaultLoginMethod,
  updateDefaultLoginMethod: async (defaultLoginMethod: string) =>
    set({ defaultLoginMethod }),
  legalUrls: environment.legalUrls,
  updateLegalUrls: async (legalUrls: EnvStoreState['legalUrls']) =>
    set({ legalUrls }),
  mdfApiUrl: environment.mdfApiUrl,
  updateMdfApiUrl: async (mdfApiUrl: string) => set({ mdfApiUrl }),
  runtimeConfigLoaded: false,
  setRuntimeConfigLoaded: (runtimeConfigLoaded: boolean) =>
    set({ runtimeConfigLoaded }),
}));
