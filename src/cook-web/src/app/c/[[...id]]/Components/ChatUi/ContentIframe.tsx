import { memo } from 'react';
import { isEqual } from 'lodash';
import { IframeSandbox, type RenderSegment } from 'markdown-flow-ui/renderer';
import { useTranslation } from 'react-i18next';
import { resolveMarkdownFlowLocale } from '@/lib/markdown-flow-locale';

interface ContentIframeProps {
  segments: RenderSegment[];
  mobileStyle: boolean;
  blockBid: string;
  //   onClickCustomButtonAfterContent?: (blockBid: string) => void;
  //   onSend: (content: OnSendContentParams, blockBid: string) => void;
  sectionTitle?: string;
}

const ContentIframe = memo(
  ({ segments, blockBid, sectionTitle }: ContentIframeProps) => {
    const { i18n } = useTranslation();
    const markdownFlowLocale = resolveMarkdownFlowLocale(
      i18n.resolvedLanguage ?? i18n.language,
    );

    return (
      <>
        {segments.map((segment, index) => {
          if (segment.type === 'text') {
            return (
              <section
                key={'text' + index}
                data-element-bid={blockBid}
                //   className='w-full h-full'
              >
                <div className='w-full h-full font-bold flex items-center justify-center text-primary'>
                  {sectionTitle}
                </div>
              </section>
            );
          }

          const iframeNode = (
            <IframeSandbox
              key={'iframe' + index}
              locale={markdownFlowLocale}
              type={segment.type}
              mode='blackboard'
              hideFullScreen
              content={segment.value}
            />
          );

          return (
            <section
              key={'sandbox' + index}
              // data-auto-animate
              data-element-bid={blockBid}
              // className={cn('content-render-theme', mobileStyle ? 'mobile' : '')}
              //   className='w-full h-full'
            >
              {segment.type === 'sandbox' ? (
                <div className='listen-sandbox-enter flex h-full w-full items-center justify-center'>
                  {iframeNode}
                </div>
              ) : (
                iframeNode
              )}
            </section>
          );
        })}
      </>
    );
  },
  (prevProps, nextProps) => {
    // Only re-render when content or layout actually changes
    return (
      isEqual(prevProps.segments, nextProps.segments) &&
      prevProps.mobileStyle === nextProps.mobileStyle &&
      prevProps.blockBid === nextProps.blockBid &&
      prevProps.sectionTitle === nextProps.sectionTitle
    );
  },
);

ContentIframe.displayName = 'ContentIframe';

export default ContentIframe;
