import { memo, useCallback } from 'react';
import { useLongPress } from 'react-use';
import { isEqual } from 'lodash';
import { ContentRender } from 'markdown-flow-ui/renderer';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { cn } from '@/lib/utils';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import {
  getAudioTrackByPosition,
  hasAudioContentInTrack,
} from '@/c-utils/audio-utils';
import { useTranslation } from 'react-i18next';
import {
  LESSON_FEEDBACK_INTERACTION_MARKER,
  LESSON_FEEDBACK_VARIABLE_NAME,
  SYS_INTERACTION_TYPE,
} from '@/c-api/studyV2';
import LessonFeedbackInteraction from './LessonFeedbackInteraction';

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
  }: ContentBlockProps) => {
    const { t } = useTranslation();
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

    const primaryTrack = getAudioTrackByPosition(item.audioTracks ?? []);
    const hasAudioContent = Boolean(hasAudioContentInTrack(primaryTrack));
    const shouldShowAudioAction = Boolean(showAudioAction);
    const isLessonFeedbackInteraction =
      item.type === ChatContentItemType.INTERACTION &&
      Boolean(item.content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER));

    return (
      <div
        className={cn(
          isLessonFeedbackInteraction ? '' : 'content-render-theme',
          mobileStyle ? 'mobile' : '',
          isLessonFeedbackInteraction ? 'mt-6' : '',
        )}
        {...(mobileStyle ? longPressEvent : {})}
      >
        {isLessonFeedbackInteraction ? (
          <p className='mb-2 text-[16px] leading-[22px] text-[var(--foreground)]'>
            {t('module.chat.lessonFeedbackPrompt')}
          </p>
        ) : null}
        {isLessonFeedbackInteraction ? (
          <LessonFeedbackInteraction
            defaultScoreText={item.defaultButtonText}
            defaultCommentText={item.defaultInputText}
            placeholder={t('module.chat.lessonFeedbackCommentPlaceholder')}
            submitLabel={confirmButtonText || t('module.renderUi.core.confirm')}
            skipLabel={t('module.chat.lessonFeedbackSkip')}
            clearLabel={t('module.chat.lessonFeedbackClearInput')}
            readonly={item.readonly}
            onSubmit={(score, comment) =>
              _onSend({
                variableName: LESSON_FEEDBACK_VARIABLE_NAME,
                buttonText: String(score),
                inputText: comment,
              })
            }
            onSkip={(score, comment) =>
              _onSend({
                variableName: LESSON_FEEDBACK_VARIABLE_NAME,
                buttonText: SYS_INTERACTION_TYPE.NEXT_CHAPTER,
                inputText: comment,
                selectedValues: score ? [String(score)] : [],
              })
            }
          />
        ) : (
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
        )}
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
