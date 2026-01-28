import { memo, useCallback } from 'react';
import { useLongPress } from 'react-use';
import { isEqual } from 'lodash';
import { ContentRender } from 'markdown-flow-ui/renderer';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { cn } from '@/lib/utils';
import type { ChatContentItem } from './useChatLogicHook';
import { AudioPlayer } from '@/components/audio/AudioPlayer';

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

    const hasAudioContent = Boolean(
      item.isAudioStreaming ||
      (item.audioSegments && item.audioSegments.length > 0) ||
      item.audioUrl,
    );

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
          defaultButtonText={item.defaultButtonText}
          defaultInputText={item.defaultInputText}
          defaultSelectedValues={item.defaultSelectedValues}
          readonly={item.readonly}
          confirmButtonText={confirmButtonText}
          copyButtonText={copyButtonText}
          copiedButtonText={copiedButtonText}
          onSend={_onSend}
        />
        {mobileStyle && hasAudioContent ? (
          <div className='mt-2 flex justify-end'>
            <AudioPlayer
              audioUrl={item.audioUrl}
              streamingSegments={item.audioSegments}
              isStreaming={Boolean(item.isAudioStreaming)}
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
    // Only re-render when content, layout, or i18n-driven button texts actually change
    return (
      prevProps.item.defaultButtonText === nextProps.item.defaultButtonText &&
      prevProps.item.defaultInputText === nextProps.item.defaultInputText &&
      isEqual(
        prevProps.item.defaultSelectedValues,
        nextProps.item.defaultSelectedValues,
      ) &&
      prevProps.item.readonly === nextProps.item.readonly &&
      prevProps.item.content === nextProps.item.content &&
      prevProps.mobileStyle === nextProps.mobileStyle &&
      prevProps.blockBid === nextProps.blockBid &&
      prevProps.confirmButtonText === nextProps.confirmButtonText &&
      prevProps.copyButtonText === nextProps.copyButtonText &&
      prevProps.copiedButtonText === nextProps.copiedButtonText &&
      Boolean(prevProps.autoPlayAudio) === Boolean(nextProps.autoPlayAudio) &&
      // Audio state (mobile only rendering)
      (prevProps.item.audioUrl ?? '') === (nextProps.item.audioUrl ?? '') &&
      Boolean(prevProps.item.isAudioStreaming) ===
        Boolean(nextProps.item.isAudioStreaming) &&
      (prevProps.item.audioSegments?.length ?? 0) ===
        (nextProps.item.audioSegments?.length ?? 0)
    );
  },
);

ContentBlock.displayName = 'ContentBlock';

export default ContentBlock;
