import { create } from 'zustand';
import { SystemStoreState } from '../types/store';

export const useSystemStore = create<SystemStoreState>((set) => ({
  language: 'en',
  channel: '',
  wechatCode: '',
  showVip: true,
  privewMode: false,
  updateChannel: (channel: string) => set({ channel }),
  updateWechatCode: (wechatCode: string) => set({ wechatCode }),
  updateLanguage: (language: string) => set({ language }),
  setShowVip: (showVip: boolean) => set({ showVip }),
  updatePrivewMode: (mode: boolean) => set({ privewMode: mode }),
}));
