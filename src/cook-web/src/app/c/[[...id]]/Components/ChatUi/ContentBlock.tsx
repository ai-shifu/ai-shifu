import { memo, useCallback, useMemo } from 'react';
import { useLongPress } from 'react-use';
import { isEqual } from 'lodash';
// TODO@XJL
// import ContentRender from '../../../../../../../../../markdown-flow-ui/src/components/ContentRender/ContentRender';
import { ContentRender, IframeSandbox } from 'markdown-flow-ui/renderer';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { splitContentSegments } from 'markdown-flow-ui/renderer';
import { cn } from '@/lib/utils';
import type { ChatContentItem } from './useChatLogicHook';
import { useSystemStore } from '@/c-store/useSystemStore';

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
    const learningMode = useSystemStore(state => state.learningMode);
    const sandboxContent = useMemo(() => {
      const segments = splitContentSegments(item.content || '');
      return segments
        .filter(seg => seg.type === 'sandbox')
        .map(seg => seg.value)
        .join('\n');
    }, [item.content]);
    console.log('sandboxContent', sandboxContent);
    return (
      <div
        className={cn('content-render-theme', mobileStyle ? 'mobile' : '')}
        {...(mobileStyle ? longPressEvent : {})}
      >
        {learningMode === 'listen' ? (
          sandboxContent ? 
          <IframeSandbox
            content={sandboxContent}
            className='content-render-iframe'
          /> : null
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
