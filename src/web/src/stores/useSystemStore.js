import { create } from 'zustand';

export const useSystemStore = create((set) => ({
  language: 'zh_CN',
}));
