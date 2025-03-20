import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { resetChapter as apiResetChapter } from 'Api/lesson.js';

export const useCourseStore = create(
  subscribeWithSelector((set,get) => ({
    courseName: '',
    updateCourseName: (courseName) => set(() => ({ courseName })),
    lessonId: null,
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
