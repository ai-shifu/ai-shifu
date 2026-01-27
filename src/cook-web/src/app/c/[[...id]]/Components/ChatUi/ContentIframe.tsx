import { memo, useCallback, useMemo } from 'react';
import { isEqual } from 'lodash';
import { IframeSandbox, splitContentSegments } from 'markdown-flow-ui/renderer';
import type { IframeSandboxProps } from 'markdown-flow-ui/renderer';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { cn } from '@/lib/utils';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';

interface ContentIframeProps {
  item: ChatContentItem;
  mobileStyle: boolean;
  blockBid: string;
  confirmButtonText?: string;
  copyButtonText?: string;
  copiedButtonText?: string;
  onClickCustomButtonAfterContent?: (blockBid: string) => void;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  sectionTitle?: string;
}

const ContentIframe = memo(
  ({
    item,
    mobileStyle,
    blockBid,
    sectionTitle,
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
      () => splitContentSegments(item.content || '', true),
      [item.content],
    );
    console.log('segments ai-shifu=====', segments);

    if (segments.length === 0 || item.type !== ChatContentItemType.CONTENT)
      return null;

    return (
      <>
        {segments.map((segment, index) =>
          segment.type === 'text' ? (
            <section
              key={'text' + index}
              data-auto-animate
              //   className='w-full h-full'
            >
              {sectionTitle}
            </section>
          ) : (
            <section
              key={'sandbox' + index}
              data-auto-animate
              // className={cn('content-render-theme', mobileStyle ? 'mobile' : '')}
              //   className='w-full h-full'
            >
              <IframeSandbox
                key={'iframe' + index}
                type={segment.type}
                mode='blackboard'
                hideFullScreen
                content={segment.value}
              />
            </section>
          ),
        )}
      </>
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
      prevProps.sectionTitle === nextProps.sectionTitle
    );
  },
);

ContentIframe.displayName = 'ContentIframe';

export default ContentIframe;
