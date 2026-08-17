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

export interface LessonUpdatePayload {
  id: string;
  name?: string;
  status?: string;
  status_value?: string;
}

export interface ChapterUpdatePayload {
  id: string;
  status: string;
  status_value: string;
}

export type LessonUpdateHandler = (params: LessonUpdatePayload) => void;
export type ChapterUpdateHandler = (params: ChapterUpdatePayload) => void;
export type LessonSelectionUpdater = (
  lessonId: string,
  forceExpand?: boolean,
) => void | Promise<void>;
export type NextLessonIdGetter = (lessonId?: string | null) => string | null;
export type ChapterNavigationHandler = (lessonId: string) => void;

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
  lessonUpdate?: LessonUpdateHandler;
  chapterUpdate?: ChapterUpdateHandler;
  updateSelectedLesson: LessonSelectionUpdater;
  getNextLessonId: NextLessonIdGetter;
  scrollToLesson: (lessonId: string) => void;
  showOutputInProgressToast: () => void;
  onPayModalOpen: () => void;
  onGoChapter: ChapterNavigationHandler;
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
  // Resolves to the audio payload on success, `null` when synthesis genuinely
  // failed, and `undefined` when the request was never attempted (cancelled,
  // superseded, or de-duplicated against an in-flight stream). Callers must not
  // treat `undefined` as a failure.
  requestAudioForBlock: (
    elementBid: string,
    options?: RequestAudioForBlockOptions,
  ) => Promise<AudioCompleteData | null | undefined>;
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
