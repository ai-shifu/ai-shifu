import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import {
  isReadModeTextContentItemReady,
  type ReadModeTypewriterCache,
} from './readModeTypewriterGate';

interface LessonPdfContentReadyOptions {
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

export const isLessonPdfContentReady = ({
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
