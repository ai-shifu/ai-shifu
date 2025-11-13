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
  baseURL: environment.apiBaseUrl,
  updateBaseURL: async (baseURL: string) => set({ baseURL }),
  logoHorizontal: environment.logoHorizontal,
  updateLogoHorizontal: async (logoHorizontal: string) =>
    set({ logoHorizontal }),
  logoVertical: environment.logoVertical,
  updateLogoVertical: async (logoVertical: string) => set({ logoVertical }),
  enableWxcode: environment.enableWechatCode.toString(),
  updateEnableWxcode: async (enableWxcode: string) => set({ enableWxcode }),
  homeUrl: environment.homeUrl,
  updateHomeUrl: async (homeUrl: string) => set({ homeUrl }),
  stripePublishableKey: environment.stripePublishableKey,
  updateStripePublishableKey: async (stripePublishableKey: string) =>
    set({ stripePublishableKey }),
  stripeEnabled: environment.stripeEnabled.toString(),
  updateStripeEnabled: async (stripeEnabled: string) => set({ stripeEnabled }),
  paymentChannels: environment.paymentChannels,
  updatePaymentChannels: async (paymentChannels: string[]) =>
    set({ paymentChannels }),
}));
