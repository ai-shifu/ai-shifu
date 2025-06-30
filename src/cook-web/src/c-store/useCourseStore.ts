import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { resetChapter as apiResetChapter } from '@/c-api/lesson';
import { CourseStoreState } from '@/c-types/store';

export const useCourseStore = create<CourseStoreState, [["zustand/subscribeWithSelector", never]]>(
  subscribeWithSelector((set,get) => ({
    courseName: '',
    updateCourseName: (courseName) => set(() => ({ courseName })),
    lessonId: undefined,
    updateLessonId: (lessonId) => set(() => ({ lessonId })),
    chapterId: '',
    updateChapterId: (newChapterId) =>  {
      const currentChapterId = get().chapterId;
      if (currentChapterId === newChapterId) {
        return;
      }


      return set(() => ({ chapterId: newChapterId }));
    },
    purchased: false,
    changePurchased: (purchased) => set(() => ({ purchased })),
    // 用于重置章节
    resetedChapterId: null,
    updateResetedChapterId: (resetedChapterId) => set(() => ({ resetedChapterId })),
    resetChapter: async (resetedChapterId) => {
      await apiResetChapter({ chapterId: resetedChapterId });
      set({ chapterId: resetedChapterId });
      set({ resetedChapterId });
    },
  })));
