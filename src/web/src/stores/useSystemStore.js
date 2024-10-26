import { create } from 'zustand';

export const useSystemStore = create((set) => ({
  language: 'en',
  channel: '',
  wechatCode: '',
  showVip: true,
  updateChannel: (channel) => set({ channel }),
  updateWechatCode: (wechatCode) => set({ wechatCode }),
  updateLanguage: (language) => set({ language }),
  setShowVip: (showVip) => set({ showVip }),
}));
