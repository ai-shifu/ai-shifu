import { memo, useEffect, useMemo, useState } from 'react';
import { isEqual } from 'lodash';
import { IframeSandbox, type RenderSegment } from 'markdown-flow-ui/renderer';

interface ContentIframeProps {
  segments: RenderSegment[];
  blockBid: string;
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

const parseStableSvgFromHtml = (raw: string): string | null => {
  if (!raw || typeof window === 'undefined' || !window.DOMParser) {
    return null;
  }
  try {
    const parser = new window.DOMParser();
    const doc = parser.parseFromString(raw, 'text/html');
    doc.querySelectorAll('script').forEach(node => node.remove());
    const svgEl = doc.querySelector('svg');
    return svgEl ? svgEl.outerHTML : null;
  } catch {
    return null;
  }
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

    // Parse with DOMParser to tolerate streaming/partial SVG safely.
    // If parsing fails, keep the last stable SVG to avoid flicker/blank flashes.
    const nextStableSvg = parseStableSvgFromHtml(svgCandidate);
    if (nextStableSvg) {
      setStableSvgHtml(nextStableSvg);
    }
  }, [svgCandidate]);

  const resolvedSvg = stableSvgHtml || svgCandidate || '';
  // Render pure SVG through sandbox mode with a stable HTML root wrapper.
  // markdown mode may keep an empty `.content-render-svg` shell for some SVGs
  // (especially style-heavy charts), which then gets pruned as blank slides.
  const sandboxHtml = resolvedSvg ? `<div>${resolvedSvg}</div>` : '';

  return (
    <IframeSandbox
      type='sandbox'
      mode='blackboard'
      hideFullScreen
      content={sandboxHtml}
    />
  );
};

const ContentIframe = memo(
  ({ segments, blockBid }: ContentIframeProps) => {
    return (
      <>
        {segments.map((segment, index) => {
          if (segment.type === 'text') {
            return null;
          }

          const segmentValue =
            typeof segment.value === 'string' ? segment.value : '';

          const isSvgSegment = /^\s*<svg\b/i.test(segmentValue);

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
    // Only re-render when content identity changes
    return (
      isEqual(prevProps.segments, nextProps.segments) &&
      prevProps.blockBid === nextProps.blockBid
    );
  },
);

ContentIframe.displayName = 'ContentIframe';

export default ContentIframe;
