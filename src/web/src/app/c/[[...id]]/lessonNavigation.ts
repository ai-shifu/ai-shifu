type LessonChapter = {
  id: string;
};

export function resolveRequestedLessonId(
  selectedLessonId?: string | null,
  lessonId?: string | null,
  urlLessonId?: string | null,
): string {
  return selectedLessonId || urlLessonId || lessonId || '';
}

type ApplyLessonSelectionParams = {
  lessonId: string;
  currentChapterId?: string;
  forceExpand?: boolean;
  getChapterByLesson: (lessonId: string) => LessonChapter | null;
  updateSelectedLesson: (lessonId: string, forceExpand?: boolean) => void;
  updateLessonId: (lessonId: string) => void;
  updateChapterId: (chapterId: string) => void;
  syncLessonUrl: (lessonId: string) => void;
};

type AppliedLessonSelection = {
  chapterId: string;
  lessonId: string;
};

export function applyLessonSelection({
  lessonId,
  currentChapterId = '',
  forceExpand = false,
  getChapterByLesson,
  updateSelectedLesson,
  updateLessonId,
  updateChapterId,
  syncLessonUrl,
}: ApplyLessonSelectionParams): AppliedLessonSelection | null {
  const chapter = getChapterByLesson(lessonId);
  if (!chapter?.id) {
    return null;
  }

  updateSelectedLesson(lessonId, forceExpand);
  updateLessonId(lessonId);
  syncLessonUrl(lessonId);

  if (chapter.id !== currentChapterId) {
    updateChapterId(chapter.id);
  }

  return {
    chapterId: chapter.id,
    lessonId,
  };
}
