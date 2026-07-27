import { type AudioCompleteData, type SSE_INPUT_TYPE } from '@/c-api/studyV2';
import { type ChatContentItem } from '@/c-types/chatUi';
import { type OnSendContentParams } from 'markdown-flow-ui/renderer';

export interface LessonFeedbackPopupState {
  open: boolean;
  outlineBid: string;
  modeKey: 'listen' | 'read' | '';
  elementBid: string;
  defaultScoreText: string;
  defaultCommentText: string;
  readonly: boolean;
}

export interface SSEParams {
  input: string | Record<string, any>;
  input_type: SSE_INPUT_TYPE;
  reload_generated_block_bid?: string;
  reload_element_bid?: string;
}

export interface RequestAudioForBlockOptions {
  listen?: boolean;
  shouldApplyResult?: () => boolean;
  onStreamSettled?: () => void;
}

export type TtsStreamCancel = (options?: { updateState?: boolean }) => void;

export interface UseChatSessionParams {
  shifuBid: string;
  outlineBid: string;
  lessonId: string;
  chapterId?: string;
  previewMode?: boolean;
  lessonHasContentUpdate?: boolean;
  isListenMode?: boolean;
  listenRequestEnabled?: boolean;
  shouldPromptLessonFeedback?: boolean;
  trackEvent: (name: string, payload?: Record<string, any>) => void;
  trackTrailProgress: (courseId: string, elementBid: string) => void;
  lessonUpdate?: (params: Record<string, any>) => void;
  chapterUpdate?: (params: Record<string, any>) => void;
  updateSelectedLesson: (lessonId: string, forceExpand?: boolean) => void;
  getNextLessonId: (lessonId?: string | null) => string | null;
  scrollToLesson: (lessonId: string) => void;
  showOutputInProgressToast: () => void;
  onPayModalOpen: () => void;
  onGoChapter: (lessonId: string) => void;
}

export interface UseChatSessionResult {
  items: ChatContentItem[];
  isLoading: boolean;
  isOutputInProgress: boolean;
  hasRunFailed: boolean;
  currentStreamingElementBid: string;
  currentTypewriterElementBid: string;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onRefresh: (elementBid: string) => void;
  toggleAskExpanded: (parentElementBid: string) => void;
  syncAskListByParentElement: (
    parentElementBid: string,
    askList: ChatContentItem[],
    options?: {
      expand?: boolean;
    },
  ) => void;
  requestAudioForBlock: (
    elementBid: string,
    options?: RequestAudioForBlockOptions,
  ) => Promise<AudioCompleteData | null>;
  reGenerateConfirm: {
    open: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  };
  lessonFeedbackPopup: {
    open: boolean;
    elementBid: string;
    defaultScoreText: string;
    defaultCommentText: string;
    readonly: boolean;
    onClose: () => void;
    onSubmit: (score: number, comment: string) => void;
  };
  showLessonUpdateNotice: boolean;
}
