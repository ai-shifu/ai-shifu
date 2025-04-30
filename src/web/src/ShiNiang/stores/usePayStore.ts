import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

interface PayStoreState {
  hasPay: boolean;
  updateHasPay: (hasPay: boolean) => void;
  orderPromotePopoverOpen: boolean;
  updateOrderPromotePopoverOpen: (open: boolean) => void;
}

export const usePayStore = create<
  PayStoreState,
  [['zustand/subscribeWithSelector', never]]
>(
  subscribeWithSelector((set) => ({
    hasPay: false,
    updateHasPay: (hasPay: boolean) => set(() => ({ hasPay })),
    orderPromotePopoverOpen: false,
    updateOrderPromotePopoverOpen: (orderPromotePopoverOpen: boolean) =>
      set(() => ({ orderPromotePopoverOpen })),
  })),
);
