import { create } from 'zustand';
import { SystemStoreState } from '../types/store';

export const useSystemStore = create<SystemStoreState>((set) => ({
  language: typeof window !== 'undefined' ? (navigator.language || navigator.languages?.[0] || 'en-US') : 'en-US',
  channel: '',
  wechatCode: '',
  showVip: true,
  previewMode: false,
  skip: false,
  updateChannel: (channel: string) => set({ channel }),
  updateWechatCode: (wechatCode: string) => set({ wechatCode }),
  updateLanguage: (language: string) => set({ language }),
  setShowVip: (showVip: boolean) => set({ showVip }),
  updatePreviewMode: (mode: boolean) => set({ previewMode: mode }),
  updateSkip: (skip: boolean) => set({ skip }),
}));
