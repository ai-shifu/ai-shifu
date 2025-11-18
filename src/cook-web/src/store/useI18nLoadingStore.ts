import { create } from 'zustand';

type I18nLoadingState = {
  isLoading: boolean;
  setLoading: (isLoading: boolean) => void;
};

export const useI18nLoadingStore = create<I18nLoadingState>(set => ({
  isLoading: true,
  setLoading: isLoading => set({ isLoading }),
}));

export const setI18nLoading = (isLoading: boolean) =>
  useI18nLoadingStore.getState().setLoading(isLoading);
