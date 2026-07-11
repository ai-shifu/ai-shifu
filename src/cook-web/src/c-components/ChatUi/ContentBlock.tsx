import { memo, useCallback } from 'react';
import { useLongPress } from 'react-use';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { useTranslation } from 'react-i18next';
import { lessonFeedbackInteractionDefaultValueOptions } from '@/c-utils/lesson-feedback-interaction-defaults';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { cn } from '@/lib/utils';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import {
  getAudioTrackByPosition,
  hasAudioContentInTrack,
} from '@/c-utils/audio-utils';
import {
  extractCustomButtonAfterContentInnerHtml,
  hasCustomButtonAfterContent,
  stripCustomButtonAfterContent,
} from '@/app/c/[[...id]]/Components/ChatUi/chatUiUtils';
import { isLessonFeedbackInteractionContent } from '@/c-utils/lesson-feedback-interaction';
import {
  isPaySystemInteractionContent,
  localizeSystemInteractionContent,
} from '@/c-utils/system-interaction';
import { CHAT_TYPEWRITER_SPEED_MS } from '@/c-constants/uiConstants';
import { resolveMarkdownFlowLocale } from '@/lib/markdown-flow-locale';
import { adaptMarkdownFlowInteractionForRender } from '@/c-utils/markdown-flow-interaction';

interface ContentBlockProps {
  item: ChatContentItem;
  mobileStyle: boolean;
  blockBid: string;
  contentRenderKey?: string;
  onClickCustomButtonAfterContent?: (blockBid: string) => void;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onLongPress?: (event: any, item: ChatContentItem) => void;
  autoPlayAudio?: boolean;
  onAudioPlayStateChange?: (blockBid: string, isPlaying: boolean) => void;
  onAudioEnded?: (blockBid: string) => void;
  showAudioAction?: boolean;
  printMode?: boolean;
  onTypeFinished?: (blockBid: string, content: string) => void;
  enableStreamingTypewriter?: boolean;
}

const ContentBlock = memo(
  ({
    item,
    mobileStyle,
    blockBid,
    contentRenderKey,
    onClickCustomButtonAfterContent,
    onSend,
    onLongPress,
    autoPlayAudio = false,
    onAudioPlayStateChange,
    onAudioEnded,
    showAudioAction = true,
    printMode = false,
    onTypeFinished,
    enableStreamingTypewriter = false,
  }: ContentBlockProps) => {
    const { t, i18n } = useTranslation();
    const markdownFlowLocale = resolveMarkdownFlowLocale(
      i18n.resolvedLanguage ?? i18n.language,
    );
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
      isLessonFeedbackInteractionContent(item.content);
    const isPayInteraction =
      item.type === ChatContentItemType.INTERACTION &&
      isPaySystemInteractionContent(item.content);
    const resolvedReadonly = printMode
      ? true
      : isPayInteraction
        ? false
        : item.readonly;
    const resolvedUserInput = isPayInteraction ? '' : item.user_input;
    const shouldEnableTypewriter =
      !printMode &&
      enableStreamingTypewriter &&
      item.shouldUseTypewriter === true &&
      item.element_type === 'text';
    const isRichContentElement =
      item.type === ChatContentItemType.CONTENT && item.element_type !== 'text';
    const localizedContent = localizeSystemInteractionContent(
      item.content || '',
      t,
    );
    const shouldRenderExternalCustomButton =
      isRichContentElement && hasCustomButtonAfterContent(localizedContent);
    const renderedContent =
      shouldEnableTypewriter || shouldRenderExternalCustomButton
        ? (stripCustomButtonAfterContent(localizedContent) ?? '')
        : localizedContent;
    const markdownFlowContent =
      item.type === ChatContentItemType.INTERACTION
        ? adaptMarkdownFlowInteractionForRender(renderedContent)
        : renderedContent;
    const externalCustomButtonInnerHtml = shouldRenderExternalCustomButton
      ? extractCustomButtonAfterContentInnerHtml(localizedContent)
      : '';
    const handleTypeFinished = useCallback(() => {
      onTypeFinished?.(blockBid, renderedContent);
    }, [blockBid, onTypeFinished, renderedContent]);

    if (isLessonFeedbackInteraction) {
      return null;
    }

    return (
      <div
        className={cn(
          'content-render-theme',
          mobileStyle ? 'mobile' : '',
          isPayInteraction && 'pay-system-interaction',
        )}
        {...(mobileStyle ? longPressEvent : {})}
      >
        <ContentRender
          key={contentRenderKey}
          locale={markdownFlowLocale}
          enableTypewriter={shouldEnableTypewriter}
          typingSpeed={CHAT_TYPEWRITER_SPEED_MS}
          content={markdownFlowContent}
          onClickCustomButtonAfterContent={handleClick}
          customRenderBar={item.customRenderBar}
          userInput={resolvedUserInput}
          interactionDefaultValueOptions={
            lessonFeedbackInteractionDefaultValueOptions
          }
          readonly={resolvedReadonly}
          onSend={_onSend}
          onTypeFinished={handleTypeFinished}
        />
        {shouldRenderExternalCustomButton && externalCustomButtonInnerHtml ? (
          <button
            type='button'
            className='content-render-custom-button-after-content mt-3 inline-flex min-w-[58px] items-center justify-center px-3 leading-none [&_img]:inline-block [&_img]:shrink-0 [&_span]:leading-none [&_span]:whitespace-nowrap'
            onClick={handleClick}
          >
            <span
              className='content-render-custom-button-after-content-inner inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none'
              dangerouslySetInnerHTML={{
                __html: externalCustomButtonInnerHtml,
              }}
            />
          </button>
        ) : null}
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
    return (
      prevProps.item.user_input === nextProps.item.user_input &&
      prevProps.item.readonly === nextProps.item.readonly &&
      prevProps.item.content === nextProps.item.content &&
      prevProps.mobileStyle === nextProps.mobileStyle &&
      prevProps.blockBid === nextProps.blockBid &&
      prevProps.contentRenderKey === nextProps.contentRenderKey &&
      prevProps.item.isHistory === nextProps.item.isHistory &&
      prevProps.item.type === nextProps.item.type &&
      prevProps.item.element_type === nextProps.item.element_type &&
      Boolean(prevProps.item.shouldUseTypewriter) ===
        Boolean(nextProps.item.shouldUseTypewriter) &&
      prevProps.item.customRenderBar === nextProps.item.customRenderBar &&
      Boolean(prevProps.enableStreamingTypewriter) ===
        Boolean(nextProps.enableStreamingTypewriter) &&
      Boolean(prevProps.autoPlayAudio) === Boolean(nextProps.autoPlayAudio) &&
      Boolean(prevProps.showAudioAction) ===
        Boolean(nextProps.showAudioAction) &&
      Boolean(prevProps.printMode) === Boolean(nextProps.printMode) &&
      prevProps.onSend === nextProps.onSend &&
      prevProps.onClickCustomButtonAfterContent ===
        nextProps.onClickCustomButtonAfterContent &&
      prevProps.onLongPress === nextProps.onLongPress &&
      prevProps.onAudioPlayStateChange === nextProps.onAudioPlayStateChange &&
      prevProps.onAudioEnded === nextProps.onAudioEnded &&
      prevProps.onTypeFinished === nextProps.onTypeFinished &&
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
