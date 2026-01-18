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
    courseAvatar: '',
    updateCourseAvatar: courseAvatar => set(() => ({ courseAvatar })),
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
    resetChapter: async lid => {
      await apiResetChapter({ lessonId: lid });
      // set({ chapterId: resetedChapterId });
      set({ resetedLessonId: lid, lessonId: lid });
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
    // Lesson time tracking
    lessonStartTime: {},
    setLessonStartTime: outlineBid => {
      set(state => ({
        lessonStartTime: {
          ...state.lessonStartTime,
          [outlineBid]: Date.now(),
        },
      }));
    },
    getLessonDuration: outlineBid => {
      const startTime = get().lessonStartTime[outlineBid];
      if (!startTime) return 0;
      return Math.floor((Date.now() - startTime) / 1000); // Return seconds
    },
    clearLessonStartTime: outlineBid => {
      set(state => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { [outlineBid]: _, ...rest } = state.lessonStartTime;
        return { lessonStartTime: rest };
      });
    },
  })),
);
