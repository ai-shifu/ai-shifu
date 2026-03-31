import { memo, useCallback } from 'react';
import { useLongPress } from 'react-use';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { lessonFeedbackInteractionDefaultValueOptions } from '@/c-utils/lesson-feedback-interaction-defaults';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { cn } from '@/lib/utils';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import {
  getAudioTrackByPosition,
  hasAudioContentInTrack,
} from '@/c-utils/audio-utils';
import { isLessonFeedbackInteractionContent } from '@/c-utils/lesson-feedback-interaction';

interface ContentBlockProps {
  item: ChatContentItem;
  mobileStyle: boolean;
  blockBid: string;
  confirmButtonText?: string;
  copyButtonText?: string;
  copiedButtonText?: string;
  onClickCustomButtonAfterContent?: (blockBid: string) => void;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onLongPress?: (event: any, item: ChatContentItem) => void;
  autoPlayAudio?: boolean;
  onAudioPlayStateChange?: (blockBid: string, isPlaying: boolean) => void;
  onAudioEnded?: (blockBid: string) => void;
  showAudioAction?: boolean;
  onTypeFinished?: (blockBid: string) => void;
}

const ContentBlock = memo(
  ({
    item,
    mobileStyle,
    blockBid,
    confirmButtonText,
    copyButtonText,
    copiedButtonText,
    onClickCustomButtonAfterContent,
    onSend,
    onLongPress,
    autoPlayAudio = false,
    onAudioPlayStateChange,
    onAudioEnded,
    showAudioAction = true,
    onTypeFinished,
  }: ContentBlockProps) => {
    const handleClick = useCallback(() => {
      onClickCustomButtonAfterContent?.(blockBid);
    }, [blockBid, onClickCustomButtonAfterContent]);

    const handleLongPress = useCallback(
      (event: any) => {
        if (onLongPress && mobileStyle) {
          onLongPress(event, item);
        }
      },
      [onLongPress, mobileStyle, item],
    );

    const longPressEvent = useLongPress(handleLongPress, {
      isPreventDefault: false,
      delay: 600,
    });

    const _onSend = useCallback(
      (content: OnSendContentParams) => {
        onSend(content, blockBid);
      },
      [onSend, blockBid],
    );
    const handleTypeFinished = useCallback(() => {
      onTypeFinished?.(blockBid);
    }, [blockBid, onTypeFinished]);

    const primaryTrack = getAudioTrackByPosition(item.audioTracks ?? []);
    const hasAudioContent = Boolean(hasAudioContentInTrack(primaryTrack));
    const shouldShowAudioAction = Boolean(showAudioAction);
    const isLessonFeedbackInteraction =
      item.type === ChatContentItemType.INTERACTION &&
      isLessonFeedbackInteractionContent(item.content);

    if (isLessonFeedbackInteraction) {
      return null;
    }

    return (
      <div
        className={cn('content-render-theme', mobileStyle ? 'mobile' : '')}
        {...(mobileStyle ? longPressEvent : {})}
      >
        <ContentRender
          enableTypewriter={false}
          content={item.content || ''}
          onClickCustomButtonAfterContent={handleClick}
          customRenderBar={item.customRenderBar}
          userInput={item.user_input}
          interactionDefaultValueOptions={
            lessonFeedbackInteractionDefaultValueOptions
          }
          readonly={item.readonly}
          confirmButtonText={confirmButtonText}
          copyButtonText={copyButtonText}
          copiedButtonText={copiedButtonText}
          onSend={_onSend}
          onTypeFinished={handleTypeFinished}
        />
        {mobileStyle && hasAudioContent && shouldShowAudioAction ? (
          <div className='mt-2 flex justify-end'>
            <AudioPlayer
              audioUrl={primaryTrack?.audioUrl}
              streamingSegments={primaryTrack?.audioSegments}
              isStreaming={Boolean(primaryTrack?.isAudioStreaming)}
              autoPlay={autoPlayAudio}
              onPlayStateChange={
                onAudioPlayStateChange
                  ? isPlaying => onAudioPlayStateChange(blockBid, isPlaying)
                  : undefined
              }
              onEnded={onAudioEnded ? () => onAudioEnded(blockBid) : undefined}
              size={16}
            />
          </div>
        ) : null}
      </div>
    );
  },
  (prevProps, nextProps) => {
    const prevPrimaryTrack = getAudioTrackByPosition(
      prevProps.item.audioTracks ?? [],
    );
    const nextPrimaryTrack = getAudioTrackByPosition(
      nextProps.item.audioTracks ?? [],
    );
    // Only re-render when content, layout, or i18n-driven button texts actually change
    return (
      prevProps.item.user_input === nextProps.item.user_input &&
      prevProps.item.readonly === nextProps.item.readonly &&
      prevProps.item.content === nextProps.item.content &&
      prevProps.mobileStyle === nextProps.mobileStyle &&
      prevProps.blockBid === nextProps.blockBid &&
      prevProps.confirmButtonText === nextProps.confirmButtonText &&
      prevProps.copyButtonText === nextProps.copyButtonText &&
      prevProps.copiedButtonText === nextProps.copiedButtonText &&
      Boolean(prevProps.autoPlayAudio) === Boolean(nextProps.autoPlayAudio) &&
      Boolean(prevProps.showAudioAction) ===
        Boolean(nextProps.showAudioAction) &&
      // Audio state (mobile only rendering)
      (prevPrimaryTrack?.audioUrl ?? '') ===
        (nextPrimaryTrack?.audioUrl ?? '') &&
      Boolean(prevPrimaryTrack?.isAudioStreaming) ===
        Boolean(nextPrimaryTrack?.isAudioStreaming) &&
      (prevPrimaryTrack?.audioSegments?.length ?? 0) ===
        (nextPrimaryTrack?.audioSegments?.length ?? 0)
    );
  },
);

ContentBlock.displayName = 'ContentBlock';

export default ContentBlock;
