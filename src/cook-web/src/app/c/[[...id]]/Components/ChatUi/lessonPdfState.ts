import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { isLessonFeedbackInteractionContent } from '@/c-utils/lesson-feedback-interaction';
import { isSystemInteractionContent } from '@/c-utils/system-interaction';
import {
  isReadModeTextContentItemReady,
  type ReadModeTypewriterCache,
} from './readModeTypewriterGate';

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

const hasPrintableLessonBody = (items: ChatContentItem[]) =>
  items.some(
    item =>
      item.type === ChatContentItemType.CONTENT &&
      item.element_bid !== 'loading' &&
      Boolean(item.content?.trim()),
  );

export const shouldExcludeLessonPdfInteraction = (content?: string | null) =>
  isLessonFeedbackInteractionContent(content) ||
  isSystemInteractionContent(content);

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
}: LessonPdfContentReadyOptions) =>
  !isSlideMode &&
  Boolean(courseName.trim()) &&
  Boolean(lessonTitle.trim()) &&
  lessonStatus === LESSON_STATUS_VALUE.COMPLETED &&
  !isLoading &&
  !isOutputInProgress &&
  !hasGenerationError &&
  !currentStreamingElementBid &&
  hasPrintableLessonBody(readModeItems) &&
  visibleReadModeItems.length === readModeItems.length &&
  readModeItems.every(item =>
    isReadModeTextContentItemReady(item, readModeTypewriterCache),
  );
