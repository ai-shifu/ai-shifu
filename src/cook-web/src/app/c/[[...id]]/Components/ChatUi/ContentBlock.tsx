import { memo, useCallback } from 'react';
import { useLongPress } from 'react-use';
import { isEqual } from 'lodash';
// TODO@XJL
// import ContentRender from '../../../../../../../../../markdown-flow-ui/src/components/ContentRender/ContentRender';
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
  // Audio props for streaming TTS (mobile only)
  showAudioPlayer?: boolean;
  autoPlayAudio?: boolean;
  onAudioPlayStateChange?: (isPlaying: boolean) => void;
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
    showAudioPlayer = false,
    autoPlayAudio = false,
    onAudioPlayStateChange,
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

    const hasAudioContent =
      item.isAudioStreaming ||
      (item.audioSegments && item.audioSegments.length > 0) ||
      Boolean(item.audioUrl);

    const shouldShowAudioPlayer =
      mobileStyle && showAudioPlayer && hasAudioContent;

    return (
      <div
        className={cn('content-render-theme', mobileStyle ? 'mobile' : '')}
        {...(mobileStyle ? longPressEvent : {})}
      >
        <ContentRender
          // typingSpeed={20}
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
        {shouldShowAudioPlayer && (
          <AudioPlayer
            audioUrl={item.audioUrl}
            streamingSegments={item.audioSegments}
            isStreaming={item.isAudioStreaming}
            previewMode={showAudioPlayer}
            autoPlay={autoPlayAudio}
            onPlayStateChange={onAudioPlayStateChange}
            size={16}
          />
        )}
      </div>
    );
  },
  (prevProps, nextProps) => {
    // Only re-render when content, layout, audio, or i18n-driven button texts actually change
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
      // Audio props - only relevant on mobile
      (!prevProps.mobileStyle ||
        (prevProps.showAudioPlayer === nextProps.showAudioPlayer &&
          (!nextProps.showAudioPlayer ||
            (prevProps.item.audioSegments?.length ===
              nextProps.item.audioSegments?.length &&
              prevProps.item.isAudioStreaming ===
                nextProps.item.isAudioStreaming &&
              prevProps.item.audioUrl === nextProps.item.audioUrl &&
              prevProps.autoPlayAudio === nextProps.autoPlayAudio))))
    );
  },
);

ContentBlock.displayName = 'ContentBlock';

export default ContentBlock;
