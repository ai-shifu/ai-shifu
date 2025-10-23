import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { resetChapter as apiResetChapter } from '@/c-api/lesson';
import { CourseStoreState } from '@/c-types/store';

export const useCourseStore = create<
  CourseStoreState,
  [['zustand/subscribeWithSelector', never]]
>(
  subscribeWithSelector((set, get) => ({
    courseName: '',
    updateCourseName: courseName => set(() => ({ courseName })),
    lessonId: undefined,
    updateLessonId: lessonId => set(() => ({ lessonId })),
    chapterId: '',
    updateChapterId: newChapterId => {
      const currentChapterId = get().chapterId;
      if (currentChapterId === newChapterId) {
        return;
      }

      return set(() => ({ chapterId: newChapterId }));
    },
    purchased: false,
    changePurchased: purchased => set(() => ({ purchased })),
    // Used for resetting a chapter
    resetedChapterId: null,
    resetedLessonId: '',
    updateResetedLessonId: resetedLessonId => set(() => ({ resetedLessonId })),
    updateResetedChapterId: resetedChapterId =>
      set(() => ({ resetedChapterId })),
    resetChapter: async resetedChapterId => {
      await apiResetChapter({ chapterId: resetedChapterId });
      // set({ chapterId: resetedChapterId });
      set({ resetedLessonId: resetedChapterId, lessonId: resetedChapterId });
    },
    payModalOpen: false,
    payModalState: {
      type: '',
      payload: {},
    },
    payModalResult: null,
    openPayModal: (options = {}) => {
      const { type = '', payload = {} } = options;
      set(() => ({
        payModalOpen: true,
        payModalState: { type, payload },
        payModalResult: null,
      }));
    },
    closePayModal: () => {
      set(() => ({ payModalOpen: false }));
    },
    setPayModalState: (state = {}) => {
      set(current => ({
        payModalState: {
          type:
            state.type !== undefined ? state.type : current.payModalState.type,
          payload:
            state.payload !== undefined
              ? state.payload
              : current.payModalState.payload,
        },
      }));
    },
    setPayModalResult: result => {
      set(() => ({ payModalResult: result }));
    },
  })),
);
