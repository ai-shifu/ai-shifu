import { memo, useCallback } from 'react';
import { useLongPress } from 'react-use';
import { isEqual } from 'lodash';
import { useTranslation } from 'react-i18next';
// TODO@XJL
// import ContentRender from '../../../../../../../../../markdown-flow-ui/src/components/ContentRender/ContentRender';
import { ContentRender, type OnSendContentParams } from 'markdown-flow-ui';
import { cn } from '@/lib/utils';
import type { ChatContentItem } from './useChatLogicHook';

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
          svgLoadingText={t('module.renderUi.core.generatingSvg')}
          onSend={_onSend}
        />
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
      prevProps.copiedButtonText === nextProps.copiedButtonText
    );
  },
);

ContentBlock.displayName = 'ContentBlock';

export default ContentBlock;
