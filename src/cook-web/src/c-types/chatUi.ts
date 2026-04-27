import type { ComponentType, ReactNode } from 'react';
import type { PreviewVariablesMap } from '@/components/lesson-preview/variableStorage';
import type {
  AudioSegmentData,
  BlockType,
  ElementType,
  LikeStatus,
  ListenSlideData,
  StudyRecordPayload,
} from '@/c-api/studyV2';
import type { AudioTrack } from '@/c-utils/audio-utils';

export enum ChatContentItemType {
  CONTENT = 'content',
  INTERACTION = 'interaction',
  ASK = 'ask',
  LIKE_STATUS = 'likeStatus',
  ERROR = 'error',
}

export interface ChatContentItem {
  content?: string;
  customRenderBar?: (() => ReactNode | null) | ComponentType<any>;
  user_input?: string;
  readonly?: boolean;
  isHistory?: boolean;
  element_bid: string;
  generated_block_bid?: string;
  ask_element_bid?: string;
  parent_element_bid?: string;
  parent_block_bid?: string;
  like_status?: LikeStatus;
  type: ChatContentItemType | BlockType | ElementType;
  ask_list?: ChatContentItem[];
  isAskExpanded?: boolean;
  generateTime?: number;
  variables?: PreviewVariablesMap;
  audioUrl?: string;
  audioTracks?: AudioTrack[];
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
  listenSlides?: ListenSlideData[];
  element_type?: ElementType;
  sequence_number?: number;
  is_marker?: boolean;
  is_new?: boolean;
  is_renderable?: boolean;
  is_speakable?: boolean;
  audio_url?: string;
  audio_segments?: AudioSegmentData[];
  payload?: StudyRecordPayload;
}
