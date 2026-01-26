import { memo, useCallback, useMemo } from 'react';
import { isEqual } from 'lodash';
import { IframeSandbox, splitContentSegments } from 'markdown-flow-ui/renderer';
import type { IframeSandboxProps } from 'markdown-flow-ui/renderer';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { cn } from '@/lib/utils';
import type { ChatContentItem } from './useChatLogicHook';

interface ContentIframeProps {
  item: ChatContentItem;
  mobileStyle: boolean;
  blockBid: string;
  confirmButtonText?: string;
  copyButtonText?: string;
  copiedButtonText?: string;
  onClickCustomButtonAfterContent?: (blockBid: string) => void;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
}

const ContentIframe = memo(
  ({
    item,
    mobileStyle,
    blockBid,
    // confirmButtonText,
    // copyButtonText,
    // copiedButtonText,
    // onClickCustomButtonAfterContent,
    // onSend,
  }: ContentIframeProps) => {
    // const handleClick = useCallback(() => {
    //   onClickCustomButtonAfterContent?.(blockBid);
    // }, [blockBid, onClickCustomButtonAfterContent]);

    // const _onSend = useCallback(
    //   (content: OnSendContentParams) => {
    //     onSend(content, blockBid);
    //   },
    //   [onSend, blockBid],
    // );

    const segments = useMemo(
      () => splitContentSegments(item.content || ''),
      [item.content],
    );
    console.log('segments ai-shifu=====', segments);
    if(segments.length === 0) return null;
    return (
      <div
        // className={cn('content-render-theme', mobileStyle ? 'mobile' : '')}
        className='w-full h-full'
      >
        {segments.map((segment, index) => (
          <IframeSandbox
            key={'iframe' + index}
            type={segment.type}
            mode='blackboard'
            content={segment.value}
          />
        ))}
        {/* <IframeSandbox
            key={blockBid}
            type={item.type}
            mode='blackboard'
            content={item.content || ''}
            // onClickCustomButtonAfterContent={handleClick}
            // customRenderBar={item.customRenderBar}
            // defaultButtonText={item.defaultButtonText}
            // defaultInputText={item.defaultInputText}
            // defaultSelectedValues={item.defaultSelectedValues}
            // readonly={item.readonly}
            // confirmButtonText={confirmButtonText}
            // copyButtonText={copyButtonText}
            // copiedButtonText={copiedButtonText}
            // onSend={_onSend}
          /> */}
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

ContentIframe.displayName = 'ContentIframe';

export default ContentIframe;
