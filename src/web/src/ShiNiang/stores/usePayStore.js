import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

export const usePayStore = create(subscribeWithSelector((set) => ({
  hasPay: false,
  updateHasPay: (hasPay) => set(() => ({ hasPay })),
  orderPromotePopoverOpen: false,
  updateOrderPromotePopoverOpen: (orderPromotePopoverOpen) => set(() => ({ orderPromotePopoverOpen })),
})))
