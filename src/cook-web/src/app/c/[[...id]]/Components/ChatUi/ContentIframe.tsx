import { memo } from 'react';
import { isEqual } from 'lodash';
import { IframeSandbox, type RenderSegment } from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';

interface ContentIframeProps {
  // item: ChatContentItem;
  segments: RenderSegment[];
  mobileStyle: boolean;
  blockBid: string;
  confirmButtonText?: string;
  copyButtonText?: string;
  copiedButtonText?: string;
  //   onClickCustomButtonAfterContent?: (blockBid: string) => void;
  //   onSend: (content: OnSendContentParams, blockBid: string) => void;
  sectionTitle?: string;
}

const ContentIframe = memo(
  ({ segments, blockBid, sectionTitle }: ContentIframeProps) => {
    return (
      <>
        {segments.map((segment, index) =>
          segment.type === 'text' ? (
            <section
              key={'text' + index}
              data-auto-animate
              data-generated-block-bid={blockBid}
              //   className='w-full h-full'
            >
              <div className='w-full h-full font-bold flex items-center justify-center text-primary'>
                {sectionTitle}
              </div>
            </section>
          ) : (
            <section
              key={'sandbox' + index}
              data-auto-animate
              data-generated-block-bid={blockBid}
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
      isEqual(prevProps.segments, nextProps.segments) &&
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
