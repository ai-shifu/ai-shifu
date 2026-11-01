import { LESSON_STATUS_VALUE } from '@/constants/course-constants';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import { isLessonFeedbackInteractionContent } from '@/lib/lesson-feedback-interaction';
import { isSystemInteractionContent } from '@/lib/system-interaction';
import {
  isReadModeTextContentItemReady,
  type ReadModeTypewriterCache,
} from './read-mode-typewriter-gate';

interface LessonPdfContentReadyOptions {
  courseName: string;
  lessonTitle: string;
  lessonStatus: string;
  isSlideMode: boolean;
  isLoading: boolean;
  isOutputInProgress: boolean;
  hasGenerationError: boolean;
  currentStreamingElementBid: string;
  readModeItems: ChatContentItem[];
  visibleReadModeItems: ChatContentItem[];
  readModeTypewriterCache: ReadModeTypewriterCache;
}

export const shouldExcludeLessonPdfInteraction = (content?: string | null) =>
  isLessonFeedbackInteractionContent(content) ||
  isSystemInteractionContent(content);

const hasPrintableLessonBody = (items: ChatContentItem[]) =>
  items.some(
    item =>
      item.element_bid !== 'loading' &&
      Boolean(item.content?.trim()) &&
      (item.type === ChatContentItemType.CONTENT ||
        (item.type === ChatContentItemType.INTERACTION &&
          !shouldExcludeLessonPdfInteraction(item.content))),
  );

export const isLessonPdfContentReady = ({
  courseName,
  lessonTitle,
  lessonStatus,
  isSlideMode,
  isLoading,
  isOutputInProgress,
  hasGenerationError,
  currentStreamingElementBid,
  readModeItems,
  visibleReadModeItems,
  readModeTypewriterCache,
}: LessonPdfContentReadyOptions) => {
  const isReadModePresentationReady =
    isSlideMode ||
    (visibleReadModeItems.length === readModeItems.length &&
      readModeItems.every(item =>
        isReadModeTextContentItemReady(item, readModeTypewriterCache),
      ));

  return (
    Boolean(courseName.trim()) &&
    Boolean(lessonTitle.trim()) &&
    lessonStatus === LESSON_STATUS_VALUE.COMPLETED &&
    !isLoading &&
    !isOutputInProgress &&
    !hasGenerationError &&
    !currentStreamingElementBid &&
    hasPrintableLessonBody(readModeItems) &&
    isReadModePresentationReady
  );
};
