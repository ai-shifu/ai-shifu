import { memo, useEffect, useMemo, useState } from 'react';
import { isEqual } from 'lodash';
import { IframeSandbox, type RenderSegment } from 'markdown-flow-ui/renderer';

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

const extractFirstSvg = (raw: string) => {
  if (!raw) {
    return null;
  }
  const match = raw.match(/<svg[\s\S]*?<\/svg>/i);
  if (!match) {
    return null;
  }
  return match[0];
};

const StableSvgSlide = ({ raw }: { raw: string }) => {
  const svgCandidate = useMemo(() => extractFirstSvg(raw) ?? raw, [raw]);
  const [stableSvgHtml, setStableSvgHtml] = useState('');

  useEffect(() => {
    if (!svgCandidate) {
      return;
    }
    if (typeof window === 'undefined') {
      return;
    }

    // Parse with the HTML parser to be tolerant to partial SVG (streaming).
    // If parsing fails, keep the last stable SVG to avoid flicker/blank flashes.
    try {
      const template = window.document.createElement('template');
      template.innerHTML = svgCandidate;
      template.content
        .querySelectorAll('script')
        .forEach(node => node.remove());
      const svgEl = template.content.querySelector('svg');
      if (!svgEl) {
        return;
      }
      setStableSvgHtml(svgEl.outerHTML);
    } catch {
      // Keep last stable SVG
    }
  }, [svgCandidate]);

  return (
    <IframeSandbox
      type='markdown'
      mode='blackboard'
      hideFullScreen
      content={stableSvgHtml || svgCandidate || ''}
    />
  );
};

const ContentIframe = memo(
  ({ segments, blockBid, sectionTitle }: ContentIframeProps) => {
    return (
      <>
        {segments.map((segment, index) => {
          if (segment.type === 'text') {
            return (
              <section
                key={'text' + index}
                data-generated-block-bid={blockBid}
                //   className='w-full h-full'
              >
                <div className='w-full h-full font-bold flex items-center justify-center text-primary'>
                  {sectionTitle}
                </div>
              </section>
            );
          }

          const segmentValue =
            typeof segment.value === 'string' ? segment.value : '';

          const isSvgSegment =
            segment.type === 'markdown' && /^\s*<svg\b/i.test(segmentValue);

          const iframeNode = isSvgSegment ? (
            <StableSvgSlide
              key={'stable-svg' + index}
              raw={segmentValue}
            />
          ) : (
            <IframeSandbox
              key={'iframe' + index}
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
              data-generated-block-bid={blockBid}
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
