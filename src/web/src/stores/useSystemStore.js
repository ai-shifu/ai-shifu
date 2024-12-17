import { create } from 'zustand';

export const useSystemStore = create((set) => ({
  language: 'en',
  channel: '',
  wechatCode: '',
  showVip: true,
  bannerUrl: '',
  collapsedBannerUrl: '',
  updateChannel: (channel) => set({ channel }),
  updateWechatCode: (wechatCode) => set({ wechatCode }),
  updateLanguage: (language) => set({ language }),
  setShowVip: (showVip) => set({ showVip }),
  setBannerUrl: (bannerUrl) => set({ bannerUrl }),
  setCollapsedBannerUrl: (collapsedBannerUrl) => set({ collapsedBannerUrl }),
}));
