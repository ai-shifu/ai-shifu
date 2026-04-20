export const EVENT_NAMES = {
  GO_TO_NAVIGATION_NODE: 'GO_TO_NAVIGATION_NODE',
  UPDATE_NAVICATION_LESSON: 'UPDATE_NAVICATION_LESSON',
  STOP_ACTIVE_LESSON_STREAM: 'STOP_ACTIVE_LESSON_STREAM',
};

export const events = new EventTarget();

export const stopActiveLessonStream = (lessonId: string) => {
  if (!lessonId) {
    return;
  }

  events.dispatchEvent(
    new CustomEvent(EVENT_NAMES.STOP_ACTIVE_LESSON_STREAM, {
      detail: { lessonId },
    }),
  );
};
