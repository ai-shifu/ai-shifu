import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { resetChapter as apiResetChapter } from 'Api/lesson';
import { CourseStoreState } from '../types/store';

export const useCourseStore = create<CourseStoreState, [["zustand/subscribeWithSelector", never]]>(
  subscribeWithSelector((set,get) => ({
    courseName: '',
    updateCourseName: (courseName: string) => set(() => ({ courseName })),
    lessonId: null,
    updateLessonId: (lessonId: string) => set(() => ({ lessonId })),
    chapterId: '',
    updateChapterId: (newChapterId: string) =>  {
      const currentChapterId = get().chapterId;
      if (currentChapterId === newChapterId) {
        return;
      }


      return set(() => ({ chapterId: newChapterId }));
    },
    purchased: false,
    changePurchased: (purchased: boolean) => set(() => ({ purchased })),
    // 用于重置章节
    resetedChapterId: null,
    updateResetedChapterId: (resetedChapterId: string) => set(() => ({ resetedChapterId })),
    resetChapter: async (resetedChapterId: string) => {
      await apiResetChapter({ chapterId: resetedChapterId });
      set({ chapterId: resetedChapterId });
      set({ resetedChapterId });
    },
  })));
